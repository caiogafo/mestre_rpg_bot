🎭 Gestão de Personagem
!criar_ficha [Nome] [FOR] [DES] [CON] [INT] [SAB] [CAR] [Raça] [Classe] [Linhagem?] — Registra raça e classe (D&D 5e SRD). Linhagem extra do bot: Humano ou Vampiro. Ex.: `!criar_ficha Elminster 10 12 14 16 10 8 Humano Mago` · raças compostas: `Meio-Elfo`, `Meio-Orc`.

!racas — Lista raças SRD aceitas.

!classes — Lista classes aceitas (Patrulheiro = Ranger).

!ficha — Exibe o painel completo com HP, Mana, Atributos, XP, ASI pendente e Equipamento.

!asi 2 [atributo] — D&D 5e: gasta 1 ASI para +2 em um atributo (for, des, con, int, sab, car). Limite 20.

!asi 1 [atributo] [atributo] — D&D 5e: gasta 1 ASI para +1 em dois atributos diferentes.

!equipar [Nome da Arma em Inglês] — Busca a arma na API oficial, define o dado de dano e o atributo de ataque (ex: !equipar greataxe).
!descanso_curto [qtd_dados=1] — Gasta Dados de Vida para recuperar HP (Bruxo também recupera Mana no descanso curto).
!descanso_longo — Restaura HP/Mana e recupera metade dos Dados de Vida (mínimo 1).

⚔️ Sistema de Combate (Jogadores)
!rolar_iniciativa — Rola 1d20 + Modificador de Destreza e entra na fila de combate.
Se o personagem for **Bárbaro nível 7+**, a iniciativa usa **vantagem** (Instinto Feral), e o bot mostra os dois dados.

!atacar [Nome do Monstro] — Realiza um ataque contra a CA do monstro usando a arma equipada. Mostra a transparência dos dados.
Regras de ataque: **1 natural = falha crítica**, **20 natural = acerto crítico** (dano dobrado).

!ordem — Lista todos os combatentes (jogadores e monstros) do maior para o menor resultado de iniciativa.

!roll [Quantidade]d[Faces] — Rolagem genérica de dados (ex: !roll 2d20).

✨ Magia e Conjuradores
!aprender [Nome da Magia em Inglês] — Adiciona uma magia ao grimório se o jogador tiver nível suficiente (ex: !aprender fireball).

!cast [slug-da-api] — Conjura magia de área sustentada (ex: `!cast spirit-guardians` = Guardiões Espirituais; depois use `!pulso_guardioes` no turno).

!cast [slug] [Nome do Monstro] — Conjura magia de alvo único (ex: `!cast fire-bolt Goblin 1`). Slugs usam hífen como na API (fire-bolt, ray-of-frost).
Também aceita nome com espaço (ex: `!cast flame strike "Young White Dragon 1"`). O bot mostra fórmula de dano e total rolado.

!pulso_guardioes — Com Spirit Guardians ativo: aplica dano em área em todos os inimigos (teste de DES vs CD).

!invocar familiar [slug] — Ex.: `!invocar familiar owl` (precisa de Find Familiar no grimório). Substitui o familiar anterior.

!invocar morto_vivo [slug] — Ex.: `!invocar morto_vivo zombie` (precisa de Animate Dead no grimório).

!iniciativa_aliado [nome] — Rola iniciativa do aliado (nome completo como o bot mostrou).

!aliado_atacar [nome do aliado] [Nome do Monstro] — O dono manda o aliado atacar (usa ataque da API).
!aliado_magias [nome do aliado] — Lista as magias disponíveis para o aliado invocado.
!aliado_cast [nome do aliado] [slug_magia] [Nome do Monstro] — O dono manda o aliado conjurar magia (ex: `!aliado_cast "Owl (familiar de Tav)" fire-bolt "Goblin 1"`).

!despedir_aliado [nome] — Remove o aliado da mesa.

!grimorio — Lista todas as magias aprendidas pelo personagem, seus danos e custos de mana.

!esquecer_magia [Nome] — Remove permanentemente uma magia do seu grimório para liberar espaço para novas.

!referencia_magias — Mostra a tabela de referência de magias (D&D 5e) para facilitar o `!aprender`.

🧛 Sistema Vampírico
!vampirismo — Mostra nível vampírico, XP vampírico e quanto falta para o próximo nível.
!alimentar [nome_alvo] — Reduz sede e concede um pouco de XP vampírico.
!ler_mente [@alvo] — Poder vampírico social (somente vampiros).
!ganhar_sangue [@Jogador] [Quantidade] — Mestre: concede XP vampírico direto (admin).

👹 Comandos do Mestre (Admin)
!definir_mestre [@Jogador] — Admin: define quem é o Mestre da Campanha do servidor.
!mestre_atual — Mostra o mestre configurado.
!remover_mestre — Mestre/Admin: remove o mestre configurado.

Após definir, o Mestre da Campanha pode usar os comandos de mestre mesmo sem ser admin.

!horda [Nome] [Qtd] — Busca na API e cria a horda com HP/CA oficiais (ex: `!horda "young white dragon" 1`).

!mob_atacar [Nome do Monstro] [@Jogador] — O monstro ataca um jogador usando os dados da API (ex: `!mob_atacar "Goblin 1" @Garrosh`).
!mob_magias [Nome do Monstro] — Lista as magias que o monstro ativo possui na API (mostra também o slug).
!mob_cast [Nome do Monstro] [slug_magia] [@Jogador] — Monstro conjura magia no alvo (ex: `!mob_cast "Mage 1" fireball @Tav`).

!status_combate — Lista o HP atual de todos os monstros vivos no campo.

!ganhar_xp [Quantidade] [@Jogador] — Mestre: adiciona XP e aplica a progressão de nível estilo D&D.
!icurar [@Jogador] [Pontos] — Mestre: cura HP direto (ex.: `!icurar @Tav +10`).

!limpar_combate — Reseta a horda e a lista de iniciativa.
!achar_item [@Jogador] [Nome do Item] [Qtd=1] [XP=0] — Mestre: adiciona item ao inventário e, se `XP>0`, concede XP ao personagem.
!inventario — Lista os itens do seu inventário.
!usar [Nome do Item] — Consome 1 item da mochila (somente remove do inventário; efeitos são aplicados pelo mestre com `!icurar`/narração).

📘 Referência de Criaturas
Veja `CRIATURAS_INVOCACAO.md` para lista/guia de slugs e invocação.