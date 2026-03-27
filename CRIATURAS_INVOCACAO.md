# Criaturas e Invocação (Mestre RPG Bot)

Este arquivo explica **quais criaturas podem ser usadas** e **como invocar** no bot.

## Regra geral

O bot usa a API oficial do D&D 5e (`dnd5eapi.co`), então você pode usar praticamente qualquer criatura disponível nessa API via **slug**.

- Exemplo de slug: `goblin`, `wolf`, `zombie`, `owl`, `skeleton`
- Slug = nome em minúsculo, espaços viram `-`

## 1) Monstros de combate (Mestre)

Comando:

`!horda <slug_monstro> <quantidade>`

Exemplos:

- `!horda goblin 3`
- `!horda wolf 2`
- `!horda ogre 1`

## 2) Familiares (Jogador conjurador)

Pré-requisito:

- Ter aprendido a magia `find familiar` no grimório.

Comando:

`!invocar familiar <slug>`

Exemplos comuns de familiar:

- `owl`
- `cat`
- `bat`
- `rat`
- `raven`

Exemplo:

`!invocar familiar owl`

## 3) Mortos-vivos controláveis (Jogador conjurador)

Pré-requisito:

- Ter aprendido `animate dead` no grimório.

Comando:

`!invocar morto_vivo <slug>`

Exemplos:

- `zombie`
- `skeleton`

Exemplo:

`!invocar morto_vivo zombie`

## 4) Como encontrar slugs válidos

Se tiver dúvida no slug:

1. Acesse o endpoint de monstros da API:
   - https://www.dnd5eapi.co/api/2014/monsters
2. Procure o `index` da criatura (esse é o slug que o bot usa).

## 5) Comandos de controle de aliados

Depois de invocar:

- `!iniciativa_aliado "NOME EXATO QUE O BOT MOSTROU"`
- `!aliado_atacar "NOME_EXATO_DO_ALIADO" "Nome do Monstro"`
- `!despedir_aliado "NOME_EXATO_DO_ALIADO"`

> Dica: copie e cole o nome exato da mensagem de invocação para evitar erro de digitação.

