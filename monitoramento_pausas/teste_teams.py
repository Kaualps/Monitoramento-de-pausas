import os, json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

url = os.environ.get("TEAMS_WEBHOOK_URL", "")
print("tamanho da URL:", len(url), "| tem sig=:", "sig=" in url)

corpo = {"text": "ALERTA DE PAUSA\nOperador: Teste Python\nRamal: 9999\nFilas: Fila A"}

req = Request(
    url,
    data=json.dumps(corpo).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    print("OK", urlopen(req, timeout=20).status)
except HTTPError as e:
    print("ERRO", e.code, e.reason)
    print(dict(e.headers))
    print(e.read().decode("utf-8", errors="replace")[:1000])