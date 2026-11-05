from flask import Flask, render_template, jsonify
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import json
import os
import threading

import config
from coletor import coletor


app = Flask(__name__)

TEAMS_WEBHOOK_URL = os.getenv(
    "TEAMS_WEBHOOK_URL",
    ""
).strip()

lock_alertas = threading.Lock()

alertas_enviados = set()
alertas_ligacoes_enviados = set()

# Último valor do cronômetro de cada ramal em ligação.
# Usado para detectar que o cronômetro zerou (nova ligação).
ultimo_tempo_ligacao = {}

historico_alertas = []
MAX_ALERTAS_HISTORICO = 200

LIMITE_LIGACAO_SEGUNDOS = 370


def enviar_teams(tipo_alerta, operador, ramal):
    if not TEAMS_WEBHOOK_URL:
        print("[TEAMS] URL não configurada.")
        return False

    # O fluxo lê o campo "text", com uma informação por linha:
    # linha 1 = título, linha 2 = operador, linha 3 = ramal.
    def limpar(valor):
        return " ".join(str(valor).split())

    texto = "\n".join([
        limpar(tipo_alerta),
        f"Operador: {limpar(operador)}",
        f"Ramal: {limpar(ramal)}",
    ])

    # Envia o texto pronto e também os campos separados,
    # assim o fluxo pode usar qualquer um dos dois.
    dados = json.dumps(
        {
            "text": texto,
            "tipo_alerta": limpar(tipo_alerta),
            "operador": limpar(operador),
            "ramal": limpar(ramal)
        },
        ensure_ascii=False
    ).encode("utf-8")

    requisicao = Request(
        TEAMS_WEBHOOK_URL,
        data=dados,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(requisicao, timeout=20) as resposta:
            print(f"[TEAMS] HTTP {resposta.status}")
            return 200 <= resposta.status < 300

    except HTTPError as erro:
        corpo = erro.read().decode(
            "utf-8",
            errors="replace"
        )

        print(f"[TEAMS] Erro HTTP: {erro.code}")
        print(f"[TEAMS] Resposta: {corpo}")
        return False

    except URLError as erro:
        print(f"[TEAMS] Erro de conexão: {erro}")
        return False

    except Exception as erro:
        print(f"[TEAMS] Erro: {erro}")
        return False


def registrar_alerta(operador, mensagem, origem):
    alerta = {
        "nome": operador.get(
            "nome",
            operador.get("operador", "")
        ),
        "ramal": operador.get("ramal", ""),
        "tempo_atual": operador.get("tempo_atual", ""),
        "mensagem": mensagem,
        "origem": origem,
        "data_hora": datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )
    }

    with lock_alertas:
        historico_alertas.append(alerta)

        if len(historico_alertas) > MAX_ALERTAS_HISTORICO:
            del historico_alertas[
                :len(historico_alertas) - MAX_ALERTAS_HISTORICO
            ]


def verificar_alertas_pausas(operadores):
    for operador in operadores:
        ramal = str(
            operador.get("ramal", "")
        ).strip()

        if not ramal:
            continue

        if operador.get("relogio_vermelho_site") is not True:
            continue

        with lock_alertas:
            if ramal in alertas_enviados:
                continue

            alertas_enviados.add(ramal)

        nome = operador.get(
            "nome",
            "Não identificado"
        )

        tipo_alerta = "🚨 ALERTA DE PAUSA EXCEDIDA"

        mensagem = (
            f"{tipo_alerta}\n"
            f"Operador: {nome}\n"
            f"Ramal: {ramal}"
        )

        print(f"[PAUSA] {nome} | Ramal: {ramal}")

        enviado = enviar_teams(
            tipo_alerta,
            nome,
            ramal
        )

        if enviado:
            registrar_alerta(
                operador,
                mensagem,
                "Pausa excedida"
            )
        else:
            with lock_alertas:
                alertas_enviados.discard(ramal)

    # Libera os ramais que saíram da pausa excedida,
    # para que possam gerar um novo alerta no futuro.
    ramais_vermelhos = {
        str(operador.get("ramal", "")).strip()
        for operador in operadores
        if operador.get("relogio_vermelho_site") is True
    }

    with lock_alertas:
        alertas_enviados.intersection_update(ramais_vermelhos)


def converter_tempo_segundos(tempo):
    if not tempo:
        return None

    try:
        partes = [
            int(parte)
            for parte in str(tempo).strip().split(":")
        ]

        if len(partes) == 3:
            return (
                partes[0] * 3600
                + partes[1] * 60
                + partes[2]
            )

        if len(partes) == 2:
            return (
                partes[0] * 60
                + partes[1]
            )

    except (ValueError, TypeError):
        return None

    return None


def obter_tempo_segundos(ligacao):
    tempo_segundos = ligacao.get("tempo_segundos")

    if tempo_segundos is None:
        tempo_segundos = converter_tempo_segundos(
            ligacao.get("tempo_atual")
        )

    return tempo_segundos


def verificar_alertas_ligacoes(ligacoes):
    for ligacao in ligacoes:
        ramal = str(
            ligacao.get("ramal", "")
        ).strip()

        if not ramal:
            continue

        nome = ligacao.get(
            "operador",
            ligacao.get("nome", "Não identificado")
        )

        tempo_segundos = obter_tempo_segundos(ligacao)

        if tempo_segundos is None:
            continue

        # Se o cronômetro voltou para trás, é uma nova ligação:
        # libera o ramal para poder alertar de novo.
        with lock_alertas:
            tempo_anterior = ultimo_tempo_ligacao.get(ramal)
            ultimo_tempo_ligacao[ramal] = tempo_segundos

            if (
                tempo_anterior is not None
                and tempo_segundos < tempo_anterior
            ):
                alertas_ligacoes_enviados.discard(ramal)

        if ligacao.get("fila_tjro") is True:
            continue

        if tempo_segundos < LIMITE_LIGACAO_SEGUNDOS:
            continue

        with lock_alertas:
            if ramal in alertas_ligacoes_enviados:
                continue

            alertas_ligacoes_enviados.add(ramal)

        tipo_alerta = "📞 ALERTA DE LIGAÇÃO EXCEDIDA"

        mensagem = (
            f"{tipo_alerta}\n"
            f"Operador: {nome}\n"
            f"Ramal: {ramal}"
        )

        print(f"[LIGAÇÃO] {nome} | Ramal: {ramal}")

        enviado = enviar_teams(
            tipo_alerta,
            nome,
            ramal
        )

        if enviado:
            registrar_alerta(
                ligacao,
                mensagem,
                "Ligação excedida"
            )
        else:
            with lock_alertas:
                alertas_ligacoes_enviados.discard(ramal)

    # Libera os ramais cuja ligação terminou (ou ficou abaixo do limite),
    # para que possam gerar um novo alerta no futuro.
    ramais_excedidos = set()

    for ligacao in ligacoes:
        tempo = obter_tempo_segundos(ligacao)

        if (
            tempo is not None
            and tempo >= LIMITE_LIGACAO_SEGUNDOS
            and ligacao.get("fila_tjro") is not True
        ):
            ramais_excedidos.add(
                str(ligacao.get("ramal", "")).strip()
            )

    ramais_em_ligacao = {
        str(ligacao.get("ramal", "")).strip()
        for ligacao in ligacoes
    }

    with lock_alertas:
        alertas_ligacoes_enviados.intersection_update(ramais_excedidos)

        # Esquece o cronômetro dos ramais que não estão em ligação.
        for ramal_antigo in list(ultimo_tempo_ligacao):
            if ramal_antigo not in ramais_em_ligacao:
                del ultimo_tempo_ligacao[ramal_antigo]


def processar_alertas_coletor(operadores, ligacoes):
    verificar_alertas_pausas(operadores)
    verificar_alertas_ligacoes(ligacoes)


coletor.definir_callback_alertas(
    processar_alertas_coletor
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dados")
def api_dados():
    estado = coletor.obter_estado()

    operadores = estado.get("operadores", [])
    ligacoes = estado.get("ligacoes", [])

    with lock_alertas:
        alertas = list(reversed(historico_alertas))

    return jsonify({
        "operadores": operadores,
        "ligacoes": ligacoes,
        "alertas": alertas,
        "conectado": estado.get("conectado", False),
        "erro": estado.get("erro"),
        "ultima_atualizacao": estado.get("ultima_atualizacao"),
        "relogios_vermelhos_site": sum(
            1
            for operador in operadores
            if operador.get("relogio_vermelho_site") is True
        )
    })


@app.route("/api/alertas")
def api_alertas():
    with lock_alertas:
        alertas = list(reversed(historico_alertas))

    return jsonify({
        "alertas": alertas
    })


@app.route("/api/status")
def api_status():
    estado = coletor.obter_estado()

    return jsonify({
        "conectado": estado.get("conectado", False),
        "erro": estado.get("erro"),
        "ultima_atualizacao": estado.get("ultima_atualizacao")
    })


if __name__ == "__main__":
    coletor.iniciar()

    app.run(
        host=getattr(config, "HOST", "127.0.0.1"),
        port=getattr(config, "PORT", 5000),
        debug=False,
        use_reloader=False
    )