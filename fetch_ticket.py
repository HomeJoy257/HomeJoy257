import requests

url = "https://tuadministradordefincas.com/ticket?token=87455844-c92c-4915-a902-34d3a9e38fdd_e20a672ca12ec1686534d2d6a9b3e474"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

session = requests.Session()
response = session.get(url, headers=headers, timeout=30, allow_redirects=True)

print(f"Status: {response.status_code}")
print(f"URL final: {response.url}")
print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
print("---CONTENIDO---")
print(response.text[:15000])
