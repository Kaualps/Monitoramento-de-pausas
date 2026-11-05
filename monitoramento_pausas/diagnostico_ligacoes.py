
import config
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=False)
        pagina = navegador.new_page()
        pagina.goto(config.SITE_URL)

        print("\nFaça login no site, se necessário.")
        print("Abra a tela que mostra operadores, pausas e ligações.")
        input("Quando a tabela estiver visível, pressione ENTER aqui...")

        linhas = pagina.locator("tr[role='row']")
        print(f"\nLinhas encontradas: {linhas.count()}")

        for i in range(linhas.count()):
            linha = linhas.nth(i)
            celulas = linha.locator("td")

            if celulas.count() < 5:
                continue

            nome = celulas.nth(0).inner_text().strip()
            ramal = celulas.nth(1).inner_text().strip()
            ligacao = celulas.nth(4)

            print("\n" + "=" * 50)
            print(f"Operador: {nome}")
            print(f"Ramal: {ramal}")
            print("HTML da coluna Ligação:")
            print(ligacao.evaluate("(elemento) => elemento.outerHTML"))

        input("\nDiagnóstico concluído. Pressione ENTER para fechar...")
        navegador.close()


if __name__ == "__main__":
    main()
