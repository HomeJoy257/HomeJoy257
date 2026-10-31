"""Descubre la URL real de cada feed en el catálogo CKAN de Renfe."""
import httpx

from .config import CKAN_URL


async def resolve_feed(client: httpx.AsyncClient, dataset_or_url: str) -> dict:
    if dataset_or_url.startswith(("http://", "https://")):
        return {"url": dataset_or_url, "resource_id": None, "dataset": None}
    r = await client.get(f"{CKAN_URL}/package_show", params={"id": dataset_or_url})
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN sin éxito: {dataset_or_url}")
    res = [x for x in payload["result"]["resources"]
           if (x.get("format") or "").upper() == "JSON" and x.get("url")]
    if len(res) != 1:
        names = [(x.get("name"), x.get("format")) for x in payload["result"]["resources"]]
        raise RuntimeError(f"{dataset_or_url}: {len(res)} recursos JSON, revisar {names}")
    return {"url": res[0]["url"], "resource_id": res[0].get("id"), "dataset": dataset_or_url}
