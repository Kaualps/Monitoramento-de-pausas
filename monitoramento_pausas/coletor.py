
import re
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

import config


class ColetorPausas:
    def __init__(self):
        self.estado = {
            "operadores": [],
            "ligacoes": [],
            "conectado": False,
            "erro": None,
            "ultima_atualizacao": None
        }

        self.lock = threading.Lock()
        self.thread = None
        self.executando = False
        self.callback_alertas = None

        self.playwright = None
        self.browser = None
        self.page = None

    def definir_callback_alertas(self, callback):
        self.callback_alertas = callback

    def iniciar(self):
        if self.executando:
            return

        self.executando = True
        self.thread = threading.Thread(
            target=self._executar,
            daemon=True
        )
        self.thread.start()

    def parar(self):
        self.executando = False

    def obter_estado(self):
        with self.lock:
            return {
                "operadores": list(self.estado["operadores"]),
                "ligacoes": list(self.estado["ligacoes"]),
                "conectado": self.estado["conectado"],
                "erro": self.estado["erro"],
                "ultima_atualizacao": self.estado["ultima_atualizacao"]
            }

    def atualizar_estado(self, operadores, ligacoes, conectado=True, erro=None):
        with self.lock:
            self.estado = {
                "operadores": operadores,
                "ligacoes": ligacoes,
                "conectado": conectado,
                "erro": erro,
                "ultima_atualizacao": datetime.now().strftime("%H:%M:%S")
            }

    def _executar(self):
        intervalo = getattr(config, "INTERVALO_COLETA", 0.5)
        site_url = getattr(config, "SITE_URL", "")

        try:
            self.playwright = sync_playwright().start()

            self.browser = self.playwright.chromium.launch(
                headless=False
            )

            self.page = self.browser.new_page()

            if site_url:
                self.page.goto(
                    site_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

            print("[COLETOR] Navegador iniciado. Aguardando coleta...")

            while self.executando:
                try:
                    operadores = self.coletar_operadores()
                    ligacoes = self.coletar_ligacoes()

                    self.atualizar_estado(
                        operadores,
                        ligacoes,
                        conectado=True
                    )

                    if self.callback_alertas:
                        self.callback_alertas(operadores, ligacoes)

                    print(
                        f"[COLETOR] {len(operadores)} operadores em pausa "
                        f"e {len(ligacoes)} ligações."
                    )

                except Exception as erro:
                    self.atualizar_estado(
                        self.obter_estado()["operadores"],
                        self.obter_estado()["ligacoes"],
                        conectado=False,
                        erro=str(erro)
                    )
                    print(f"[COLETOR] Erro na coleta: {erro}")

                time.sleep(intervalo)

        except Exception as erro:
            self.atualizar_estado(
                [],
                [],
                conectado=False,
                erro=str(erro)
            )
            print(f"[COLETOR] Erro ao iniciar navegador: {erro}")

        finally:
            self.executando = False

            if self.browser:
                self.browser.close()

            if self.playwright:
                self.playwright.stop()

    def converter_tempo(self, tempo):
        if not tempo:
            return 0

        partes = tempo.split(":")

        try:
            partes = [int(p) for p in partes]

            if len(partes) == 3:
                horas, minutos, segundos = partes
                return horas * 3600 + minutos * 60 + segundos

            if len(partes) == 2:
                minutos, segundos = partes
                return minutos * 60 + segundos

        except (ValueError, TypeError):
            return 0

        return 0

    def extrair_tempo(self, texto):
        if not texto:
            return None

        resultado = re.findall(
            r"(?<!\d)(?:\d{1,2}:)?\d{1,2}:\d{2}(?!\d)",
            texto
        )

        return resultado[-1] if resultado else None

    def cor_vermelho(self, cor):
        if not cor:
            return False

        rgb = re.search(
            r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)",
            cor
        )

        if not rgb:
            return False

        r, g, b = map(int, rgb.groups())

        return r >= 150 and r > g * 1.3 and r > b * 1.3

    def verificar_relogio_vermelho(self, elemento):
        try:
            return elemento.evaluate("""
                elemento => {
                    const elementos = [
                        elemento,
                        ...elemento.querySelectorAll("*")
                    ];

                    return elementos.some(item => {
                        const estilo = window.getComputedStyle(item);

                        const cores = [
                            estilo.color,
                            estilo.backgroundColor,
                            estilo.fill,
                            estilo.stroke
                        ];

                        return cores.some(cor => {
                            const rgb = cor.match(
                                /rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)/
                            );

                            if (!rgb) return false;

                            const r = Number(rgb[1]);
                            const g = Number(rgb[2]);
                            const b = Number(rgb[3]);

                            return r >= 150 &&
                                   r > g * 1.3 &&
                                   r > b * 1.3;
                        });
                    });
                }
            """)
        except Exception:
            return False

    def coletar_operadores(self):
        operadores = []

        linhas = self.page.locator("tr[role='row']")

        for i in range(linhas.count()):
            linha = linhas.nth(i)
            colunas = linha.locator("td")

            if colunas.count() < 2:
                continue

            nome = colunas.nth(0).inner_text().strip()
            ramal = colunas.nth(1).inner_text().strip()

            if not nome or not ramal:
                continue

            relogio = linha.locator(".pause-timer-2")

            if relogio.count() == 0:
                continue

            elemento_relogio = relogio.first

            texto_tempo = elemento_relogio.inner_text().strip()
            tempo_atual = self.extrair_tempo(texto_tempo)

            if not tempo_atual:
                continue

            tempo_segundos = self.converter_tempo(tempo_atual)

            vermelho = self.verificar_relogio_vermelho(
                elemento_relogio
            )

            operadores.append({
                "nome": nome,
                "ramal": ramal,
                "em_pausa": True,
                "relogio_vermelho_site": vermelho,
                "tempo_atual": tempo_atual,
                "tempo_segundos": tempo_segundos
            })

        return operadores

    def icone_telefone_verde(self, elemento):
        try:
            return elemento.evaluate("""
                elemento => {
                    const elementos = [
                        elemento,
                        ...elemento.querySelectorAll("*")
                    ];

                    return elementos.some(item => {
                        const estilo = window.getComputedStyle(item);

                        const cores = [
                            estilo.color,
                            estilo.fill,
                            estilo.stroke
                        ];

                        return cores.some(cor => {
                            const rgb = cor.match(
                                /rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)/
                            );

                            if (!rgb) return false;

                            const r = Number(rgb[1]);
                            const g = Number(rgb[2]);
                            const b = Number(rgb[3]);

                            return g >= 100 &&
                                   g > r * 1.3 &&
                                   g > b * 1.1;
                        });
                    });
                }
            """)
        except Exception:
            return False

    def coletar_ligacoes(self):
        ligacoes = []

        linhas = self.page.locator("tr[role='row']")

        for i in range(linhas.count()):
            linha = linhas.nth(i)
            colunas = linha.locator("td")

            if colunas.count() < 5:
                continue

            nome = colunas.nth(0).inner_text().strip()
            ramal = colunas.nth(1).inner_text().strip()
            texto_fila = colunas.nth(3).inner_text().strip()

            coluna_ligacao = colunas.nth(4)

            telefone_verde = self.icone_telefone_verde(
                coluna_ligacao
            )

            if not telefone_verde:
                continue

            texto_ligacao = coluna_ligacao.inner_text().strip()
            tempo_atual = self.extrair_tempo(texto_ligacao)

            if not tempo_atual:
                continue

            tempo_segundos = self.converter_tempo(tempo_atual)

            ligacoes.append({
                "operador": nome,
                "ramal": ramal,
                "estado": "Em ligação",
                "fila": texto_fila,
                "fila_tjro": "TJRO" in texto_fila.upper(),
                "tempo_atual": tempo_atual,
                "tempo_segundos": tempo_segundos
            })

        return ligacoes


coletor = ColetorPausas()
