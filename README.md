# Mestre RPG Bot

Bot de Discord em Python para auxiliar mesas de **D&D 5e** (fichas, combate, magias, XP, etc.).

## Requisitos

- Python **3.13+**
- [Poetry](https://python-poetry.org/) para dependências

## Configuração

1. Clone o repositório.
2. Copie o arquivo de ambiente e coloque o token do bot:

   ```bash
   copy .env.example .env
   ```

   Edite `.env` e defina `DISCORD_TOKEN`.

3. Instale dependências e rode:

   ```bash
   poetry install
   poetry run python main.py
   ```

O SQLite (`*.db`) é criado localmente e não entra no Git (está no `.gitignore`).

## Comandos

Veja `Comandos.md` na raiz do projeto para a lista de comandos do bot.

## Licença

Uso pessoal / projeto de mesa — ajuste conforme sua necessidade.
