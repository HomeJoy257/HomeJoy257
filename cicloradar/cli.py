"""
CLI de CicloRadar.

  python -m cicloradar.cli demo      # pipeline completo con datos sintéticos (offline)
  python -m cicloradar.cli run       # fetch en vivo + índice + alerta (requiere egress)
  python -m cicloradar.cli check     # diagnóstico de entorno (keys, egress)
  python -m cicloradar.cli history   # vuelca el histórico almacenado

Flags de `run`/`demo`:
  --save     guarda el histórico en SQLite
  --notify   envía la alerta a Telegram (si no es VERDE)
  --json     salida JSON en vez de informe de texto
"""

from __future__ import annotations

import json
import sys

from .config import REQUIRED_EGRESS_HOSTS, settings
from .constants.cfc_chronology import CFC_RECESSIONS, CHRONOLOGY_VERSION
from .data.demo import demo_series
from .data.fetcher import FetchResult, fetch_all
from .engine.aggregate import compute
from .engine.alert import evaluate
from . import report


def _window_summary(series: dict, window: int):
    """Calcula índice + alerta para una ventana de momentum dada."""
    history = compute(series, window)
    if not history:
        return None
    return history, evaluate(history), window


def _run_pipeline(series: dict, fetch: FetchResult | None):
    primary = _window_summary(series, settings.momentum_window_months)
    if primary is None:
        print("⚠️  Cobertura insuficiente: no se puede emitir índice.")
        return None, None, None, None
    alt = _window_summary(series, settings.momentum_window_alt)
    history, alert, _ = primary
    return history, alert, fetch, alt


def _emit(history, alert, fetch, args, alt=None):
    last = history[-1]
    if "--json" in args:
        out = {
            "period": last.period.isoformat(),
            "momentum_window": settings.momentum_window_months,
            "index": last.index,
            "state": alert.state.value,
            "trigger": alert.trigger,
            "delta": alert.delta,
            "coverage": last.coverage,
            "blocks_available": last.blocks_available,
            "block_scores": last.block_scores,
            "drivers": last.drivers(),
            "reason": alert.reason,
        }
        if alt:
            alt_hist, alt_alert, alt_w = alt
            alt_last = alt_hist[-1]
            out["alt_window"] = {
                "momentum_window": alt_w,
                "index": alt_last.index,
                "state": alt_alert.state.value,
                "delta": alt_alert.delta,
                "trigger": alt_alert.trigger,
            }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(report.render(last, alert, fetch, primary_window=settings.momentum_window_months,
                            alt=alt))

    if "--save" in args:
        from .storage import history as store
        store.save_history(history)
        store.save_point(last, alert)
        print(f"\n💾 Guardado en {settings.db_path} ({len(history)} periodos).")

    if "--notify" in args:
        from .notify.telegram import notify
        sent = notify(last, alert)
        print(f"\n📨 Telegram: {'enviado' if sent else 'no enviado (VERDE o sin token)'}.")


def cmd_demo(args):
    print("⚙️  Modo DEMO (datos sintéticos deterministas — NO reales)\n", file=sys.stderr)
    series = demo_series()
    history, alert, _, alt = _run_pipeline(series, None)
    if history:
        _emit(history, alert, None, args, alt)


def cmd_run(args):
    print("📡 Fetch en vivo de todas las fuentes...\n", file=sys.stderr)
    fetch = fetch_all()
    if not fetch.series:
        print("❌ No se obtuvo ninguna serie. ¿Egress habilitado? ¿FRED_API_KEY?")
        cmd_check(args)
        return
    history, alert, fetch, alt = _run_pipeline(fetch.series, fetch)
    if history:
        _emit(history, alert, fetch, args, alt)


def cmd_check(args):
    print("🔎 Diagnóstico de entorno\n" + "─" * 40)
    print(f"FRED_API_KEY        : {'✅' if settings.fred_api_key else '❌ falta'}")
    print(f"TELEGRAM_BOT_TOKEN  : {'✅' if settings.telegram_token else '❌ falta'}")
    print(f"TELEGRAM_CHAT_ID    : {'✅' if settings.telegram_chat_id else '❌ falta'}")
    print(f"Ventana momentum    : {settings.momentum_window_months} meses (primaria) "
          f"+ {settings.momentum_window_alt} meses (secundaria)")
    print(f"Umbrales            : ámbar={settings.amber_level} rojo={settings.red_level}")
    print(f"Cronología CFC      : v{CHRONOLOGY_VERSION} ({len(CFC_RECESSIONS)} recesiones)")
    print("\nHosts que deben estar en el allowlist de egress:")
    for h in REQUIRED_EGRESS_HOSTS:
        print(f"  • {h}")
    print("\nProbando conectividad (sin clave)...")
    from .data.http import get, EgressBlocked
    for h in ("api.stlouisfed.org", "data-api.ecb.europa.eu"):
        try:
            get(f"https://{h}/", timeout=8)
            print(f"  {h}: ✅ alcanzable")
        except EgressBlocked:
            print(f"  {h}: ❌ bloqueado por egress")
        except Exception as e:  # noqa: BLE001
            print(f"  {h}: ⚠️  {type(e).__name__}")


def cmd_history(args):
    import sqlite3
    try:
        c = sqlite3.connect(settings.db_path)
        rows = c.execute(
            "SELECT period, index_value, blocks_available, state, trigger "
            "FROM index_history ORDER BY period DESC LIMIT 24").fetchall()
    except sqlite3.OperationalError:
        print("Sin histórico todavía. Ejecuta `run --save` o `demo --save`.")
        return
    print(f"{'periodo':<12}{'índice':>7}{'cob':>5}  estado")
    for p, idx, cov, state, trig in rows:
        print(f"{p:<12}{idx:>7}{cov:>4}/5  {state or '-'} ({trig or '-'})")


def cmd_verify(args):
    """Verifica el cálculo de momentum sobre datos reales o de muestra.

      verify                          -> muestra fija + comprobación a mano
      verify --csv datos.csv          -> CSV del usuario 'periodo,valor' (REAL, sin red)
      verify --fred IRLTLT01ESM156N   -> serie FRED en vivo (egress + FRED_API_KEY)
      verify --indicator hy_spread    -> el indicador del registro (en vivo)
    """
    from . import verify as v

    windows = (settings.momentum_window_months, settings.momentum_window_alt)

    def _opt(flag):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None

    csv_path = _opt("--csv")
    fred_id = _opt("--fred")
    ind_key = _opt("--indicator")

    if csv_path:
        s = v.from_csv(csv_path)
        print(f"📄 Datos REALES desde CSV: {csv_path}\n")
        print(v.trace_momentum(s, windows, tail=int(_opt("--tail") or 18)))
        return
    if fred_id or ind_key:
        from .data import fred
        from .constants.series_registry import get_indicator
        sid = fred_id or get_indicator(ind_key).primary().series_id
        print(f"📡 Fetch en vivo FRED: {sid}\n")
        try:
            s = fred.get_series(sid).to_monthly()
            print(v.trace_momentum(s, windows, tail=int(_opt("--tail") or 18)))
        except Exception as e:  # noqa: BLE001
            print(f"❌ No se pudo fetchear ({type(e).__name__}: {e}).")
            print("   ¿Egress abierto a api.stlouisfed.org y FRED_API_KEY puesta?")
        return

    # Por defecto: muestra fija + comprobación a mano (offline, auditable).
    print("🧪 Verificación del motor de momentum (ventanas "
          f"{windows[0]}m y {windows[1]}m)\n")
    print(v.trace_momentum(v.sample(), windows, tail=12))
    print()
    print(v.hand_check())
    print("\n💡 Para datos REALES sin red: `verify --csv tus_datos.csv`")
    print("   (CSV con líneas 'YYYY-MM,valor'). Pásame el CSV y lo corro aquí.")


_COMMANDS = {"demo": cmd_demo, "run": cmd_run, "check": cmd_check,
             "history": cmd_history, "verify": cmd_verify}


def main(argv: list[str] | None = None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "demo"
    fn = _COMMANDS.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(1)
    fn(argv[1:])


if __name__ == "__main__":
    main()
