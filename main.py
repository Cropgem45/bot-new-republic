import os
import json
import asyncio
import io
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

# =========================================================
# TOKEN (USE VARIÁVEL DE AMBIENTE)
# =========================================================
# ✅ No Windows (PowerShell):
# setx DISCORD_TOKEN "SEU_TOKEN_NOVO_AQUI"
# Depois feche e abra o terminal de novo.
TOKEN = os.getenv("DISCORD_TOKEN")
# =========================================================
# CONFIG
# =========================================================
LOGO = "https://i.imgur.com/LAQ6bZd.png"

CARGO_VISITANTE = "👤「Visitante 」"
CARGO_MEMBRO = "✨「New Republic」"
CARGO_STAFF = "👤「Equipe Staff」"

CATEGORIA_TICKET = "Tickets"
CANAL_LOG = "logs"

CANAL_WL_STAFF = "respostas-wl"
CANAL_WL_APROVADAS = "✅・wl-aprovadas"
CANAL_WL_REPROVADAS = "❌・wl-reprovadas"
CARGO_CIDADAO = "🌃「Cidadão 」"
CATEGORIA_WL = "WHITELIST"

TEMPO_WL_POR_PERGUNTA = 600  # 10 min

# ✅ Coloque o ID do seu servidor aqui (para sync rápido)
# Se quiser global (mais lento), use: GUILD_ID = None
GUILD_ID = 1475152340326813796

DATA_DIR = Path(".")
TICKETS_COUNTER_FILE = DATA_DIR / "tickets.json"
TICKETS_DB_FILE = DATA_DIR / "ticket_data.json"
WL_LOCK_FILE = DATA_DIR / "wl_lock.json"

# =========================================================
# CORES
# =========================================================
ROXO = 0x7A35FF
VERDE = 0x00FF99
VERMELHO = 0xFF0000
CINZA = 0x2B2D31
AZUL = 0x3498DB

# =========================================================
# INTENTS
# =========================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

# =========================================================
# JSON HELPERS
# =========================================================
def _load_json(path: Path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

# =========================================================
# WL LOCK
# =========================================================
def is_wl_locked() -> bool:
    data = _load_json(WL_LOCK_FILE, {"locked": False})
    return bool(data.get("locked", False))

def set_wl_locked(value: bool):
    _save_json(WL_LOCK_FILE, {"locked": bool(value)})

# =========================================================
# HELPERS DISCORD
# =========================================================
def get_text_channel_by_name(guild: discord.Guild, name: str):
    return discord.utils.get(guild.text_channels, name=name)

def get_log_channel(guild: discord.Guild):
    return get_text_channel_by_name(guild, CANAL_LOG)

def get_wl_staff_channel(guild: discord.Guild):
    return get_text_channel_by_name(guild, CANAL_WL_STAFF)

def get_wl_aprovadas_channel(guild: discord.Guild):
    return get_text_channel_by_name(guild, CANAL_WL_APROVADAS)

def get_wl_reprovadas_channel(guild: discord.Guild):
    return get_text_channel_by_name(guild, CANAL_WL_REPROVADAS)

def is_staff(member: discord.Member) -> bool:
    staff_role = discord.utils.get(member.guild.roles, name=CARGO_STAFF)
    return bool(staff_role and staff_role in member.roles)

def _slug_channel_name(text: str) -> str:
    # slug simples e seguro pra nome de canal
    s = text.lower().strip()
    s = s.replace("ç", "c").replace("ã", "a").replace("á", "a").replace("à", "a").replace("â", "a")
    s = s.replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ô", "o").replace("ú", "u")
    s = s.replace("/", "-").replace("|", "-").replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return "".join([c for c in s if c.isalnum() or c == "-"]).strip("-") or "ticket"

async def ensure_log_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    ch = get_log_channel(guild)
    if ch:
        return ch
    # tenta criar se não existir
    try:
        # se existir categoria Tickets, joga lá; se não, cria solto mesmo
        categoria = discord.utils.get(guild.categories, name=CATEGORIA_TICKET)
        ch = await guild.create_text_channel(
            name=CANAL_LOG,
            category=categoria,
            reason="Canal de logs do bot"
        )
        return ch
    except Exception:
        return None

# =========================================================
# TICKETS DB
# =========================================================
def gerar_ticket_numero() -> int:
    data = _load_json(TICKETS_COUNTER_FILE, {"contador": 0})
    data["contador"] = int(data.get("contador", 0)) + 1
    _save_json(TICKETS_COUNTER_FILE, data)
    return data["contador"]

def load_ticket_db() -> dict:
    return _load_json(TICKETS_DB_FILE, {})

def save_ticket_db(data: dict):
    _save_json(TICKETS_DB_FILE, data)

def set_ticket_data(channel_id: int, user_id: int, tipo: str, ticket_num: int):
    db = load_ticket_db()
    db[str(channel_id)] = {"user_id": user_id, "tipo": tipo, "ticket_num": ticket_num, "assumido_por": None}
    save_ticket_db(db)

def get_ticket_data(channel_id: int):
    return load_ticket_db().get(str(channel_id))

def update_ticket_data(channel_id: int, **kwargs):
    db = load_ticket_db()
    key = str(channel_id)
    if key not in db:
        return
    db[key].update(kwargs)
    save_ticket_db(db)

def delete_ticket_data(channel_id: int):
    db = load_ticket_db()
    key = str(channel_id)
    if key in db:
        del db[key]
        save_ticket_db(db)

# =========================================================
# EMBED: ANÚNCIO
# =========================================================
def build_announcement_embed(titulo: str, mensagem: str) -> discord.Embed:
    mensagem = mensagem.replace("\\n", "\n")
    e = discord.Embed(title=titulo, description=mensagem, color=ROXO)
    e.set_thumbnail(url=LOGO)
    e.set_footer(text="New Republic Roleplay")
    return e

# =========================================================
# HELPERS: TEXTO (changelog)
# =========================================================
def norm(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text

# =========================================================
# VIEW: REGISTRO (MELHORADO, MENOS VAZIO)
# =========================================================
class VerificarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Registrar-se", emoji="✅", style=discord.ButtonStyle.green, custom_id="nr_registrar")
    async def registrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        cargo_visitante = discord.utils.get(interaction.guild.roles, name=CARGO_VISITANTE)
        cargo_membro = discord.utils.get(interaction.guild.roles, name=CARGO_MEMBRO)

        if not cargo_membro:
            await interaction.followup.send("❌ Cargo de membro não encontrado.", ephemeral=True)
            return

        if cargo_membro in interaction.user.roles:
            await interaction.followup.send("⚠️ Você já está registrado.", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(cargo_membro, reason="Registro New Republic")
            if cargo_visitante and cargo_visitante in interaction.user.roles:
                await interaction.user.remove_roles(cargo_visitante, reason="Registro New Republic")
        except discord.Forbidden:
            await interaction.followup.send("❌ Sem permissão para gerenciar cargos (hierarquia do bot).", ephemeral=True)
            return

        await interaction.followup.send("✅ Registro concluído! Bem-vindo(a) à New Republic.", ephemeral=True)

# =========================================================
# VIEW: TICKETS
# =========================================================
class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🆘", description="Dúvidas e ajuda geral"),
            discord.SelectOption(label="Denúncia", emoji="🚨", description="Reportar algo sério"),
            discord.SelectOption(label="Bug", emoji="🐞", description="Problemas e erros do servidor"),
            discord.SelectOption(label="Assumir Fac/Corp", emoji="🏢", description="Atendimento para assumir facção/corporação"),
            discord.SelectOption(label="Outro", emoji="📩", description="Qualquer outro assunto"),
        ]
        super().__init__(
            placeholder="Selecione o tipo de atendimento…",
            options=options,
            custom_id="nr_ticket_select",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user
        tipo = self.values[0]

        categoria = discord.utils.get(guild.categories, name=CATEGORIA_TICKET)
        if not categoria:
            try:
                categoria = await guild.create_category(CATEGORIA_TICKET)
            except discord.Forbidden:
                await interaction.followup.send("❌ Sem permissão para criar categoria.", ephemeral=True)
                return

        staff = discord.utils.get(guild.roles, name=CARGO_STAFF)
        ticket_id = gerar_ticket_numero()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        tipo_slug = _slug_channel_name(tipo)
        canal_nome = f"{tipo_slug}-{ticket_id:03d}"

        try:
            canal = await guild.create_text_channel(name=canal_nome, category=categoria, overwrites=overwrites)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sem permissão para criar canal.", ephemeral=True)
            return

        set_ticket_data(canal.id, user.id, tipo, ticket_id)

        embed = discord.Embed(title=f"🎫 Ticket #{ticket_id}", color=CINZA)
        embed.add_field(name="Usuário", value=user.mention, inline=True)
        embed.add_field(name="Tipo", value=tipo, inline=True)
        embed.add_field(name="Status", value="🟡 Aguardando Staff", inline=True)
        embed.add_field(name="Como funciona", value="Um staff vai assumir e te atender aqui. Evite spam.", inline=False)
        embed.set_thumbnail(url=LOGO)

        await canal.send(embed=embed, view=TicketControls())

        # ✅ Envia log de criação
        log = await ensure_log_channel(guild)
        if log:
            try:
                e = discord.Embed(title="🆕 Ticket Criado", color=AZUL)
                e.add_field(name="Canal", value=canal.mention, inline=False)
                e.add_field(name="Autor", value=user.mention, inline=True)
                e.add_field(name="Tipo", value=tipo, inline=True)
                e.add_field(name="Ticket #", value=str(ticket_id), inline=True)
                e.set_thumbnail(url=LOGO)
                await log.send(embed=e)
            except Exception:
                pass

        await interaction.followup.send(f"✅ Ticket criado: {canal.mention}", ephemeral=True)

        # ✅ Reset do Select
        try:
            if interaction.message:
                await interaction.message.edit(view=TicketPanel())
        except Exception:
            pass

class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.blurple, emoji="👮", custom_id="nr_ticket_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if not is_staff(interaction.user):
            await interaction.followup.send("❌ Apenas staff pode assumir.", ephemeral=True)
            return

        info = get_ticket_data(interaction.channel.id)
        if not info:
            await interaction.followup.send("❌ Ticket não encontrado no sistema.", ephemeral=True)
            return

        if info.get("assumido_por"):
            await interaction.followup.send("⚠️ Esse ticket já foi assumido.", ephemeral=True)
            return

        update_ticket_data(interaction.channel.id, assumido_por=interaction.user.id)

        # ✅ Renomeia canal: tipo-staff
        try:
            tipo_slug = _slug_channel_name(info.get("tipo", "ticket"))
            staff_slug = _slug_channel_name(interaction.user.name)
            novo_nome = f"{tipo_slug}-{staff_slug}"
            await interaction.channel.edit(name=novo_nome, reason="Ticket assumido pela staff")
        except Exception:
            pass

        # ✅ Atualiza embed
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            try:
                embed.set_field_at(2, name="Status", value=f"🟢 Assumido por {interaction.user.mention}", inline=True)
            except Exception:
                embed.add_field(name="Status", value=f"🟢 Assumido por {interaction.user.mention}", inline=True)

            button.disabled = True
            button.label = "Ticket Assumido"
            button.style = discord.ButtonStyle.green
            await interaction.message.edit(embed=embed, view=self)

        # ✅ Log
        log = await ensure_log_channel(interaction.guild)
        if log:
            try:
                e = discord.Embed(title="👮 Ticket Assumido", color=VERDE)
                e.add_field(name="Canal", value=interaction.channel.mention, inline=False)
                e.add_field(name="Staff", value=interaction.user.mention, inline=True)
                e.add_field(name="Tipo", value=info.get("tipo", "-"), inline=True)
                e.set_thumbnail(url=LOGO)
                await log.send(embed=e)
            except Exception:
                pass

        await interaction.followup.send("✅ Ticket assumido.", ephemeral=True)

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="nr_ticket_fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        info = get_ticket_data(interaction.channel.id)
        if not info:
            await interaction.response.send_message("❌ Ticket inválido.", ephemeral=True)
            return

        is_autor = (interaction.user.id == info["user_id"])
        is_staff_ = is_staff(interaction.user)
        if not (is_autor or is_staff_):
            await interaction.response.send_message("❌ Apenas o autor ou staff pode fechar.", ephemeral=True)
            return

        autor_id = info["user_id"]

        class MotivoModal(discord.ui.Modal, title="Encerrar Ticket"):
            def __init__(self):
                super().__init__(timeout=None)
                self.motivo = discord.ui.TextInput(
                    label="Motivo (curto e claro)",
                    style=discord.TextStyle.paragraph,
                    max_length=300,
                    required=True
                )
                self.add_item(self.motivo)

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)

                canal = modal_interaction.channel
                guild = modal_interaction.guild
                autor = guild.get_member(autor_id)

                linhas = []
                async for m in canal.history(limit=None, oldest_first=True):
                    anexos = ""
                    if m.attachments:
                        anexos = " | Anexos: " + ", ".join([a.url for a in m.attachments])
                    conteudo = m.content if m.content else ""
                    if m.embeds:
                        conteudo += f" | (embeds: {len(m.embeds)})"
                    linhas.append(
                        f"[{m.created_at.strftime('%d/%m %H:%M')}] {m.author} ({m.author.id}): {conteudo}{anexos}"
                    )

                transcript = "\n".join(linhas) if linhas else "Sem mensagens no ticket."
                file_log = discord.File(
                    io.BytesIO(transcript.encode("utf-8")),
                    filename=f"{canal.name}.txt"
                )

                e = discord.Embed(title="🔒 Ticket Fechado", color=VERMELHO)
                e.add_field(name="Canal", value=f"#{canal.name}", inline=False)
                e.add_field(name="Fechado por", value=modal_interaction.user.mention, inline=True)
                e.add_field(name="Autor", value=(autor.mention if autor else f"ID: {autor_id}"), inline=True)
                e.add_field(name="Motivo", value=self.motivo.value, inline=False)
                e.set_thumbnail(url=LOGO)

                log = await ensure_log_channel(guild)
                if log:
                    try:
                        await log.send(embed=e, file=file_log)
                    except Exception:
                        try:
                            await log.send(embed=e)
                        except Exception:
                            pass

                dm_ok = False
                if autor:
                    try:
                        dm_file = discord.File(
                            io.BytesIO(transcript.encode("utf-8")),
                            filename=f"{canal.name}.txt"
                        )

                        dm_embed = discord.Embed(
                            title="📩 Seu ticket foi encerrado",
                            description=(
                                f"**Servidor:** {guild.name}\n"
                                f"**Ticket:** `#{canal.name}`\n"
                                f"**Fechado por:** {modal_interaction.user}\n\n"
                                f"**Motivo:**\n{self.motivo.value}"
                            ),
                            color=ROXO
                        )
                        dm_embed.set_thumbnail(url=LOGO)
                        dm_embed.set_footer(text="New Republic Roleplay • Suporte")

                        await autor.send(embed=dm_embed, file=dm_file)
                        dm_ok = True
                    except discord.Forbidden:
                        dm_ok = False
                    except Exception:
                        dm_ok = False

                if log and not dm_ok:
                    try:
                        await log.send(f"⚠️ Não consegui enviar DM para o autor do ticket. Autor ID: `{autor_id}`")
                    except Exception:
                        pass

                delete_ticket_data(canal.id)
                await modal_interaction.followup.send("🔒 Ticket encerrado.", ephemeral=True)
                await asyncio.sleep(2)
                await canal.delete(reason="Ticket encerrado")

        await interaction.response.send_modal(MotivoModal())

# =========================================================
# WL: LOCK (anti dupla execução)
# =========================================================
ACTIVE_WL: set[int] = set()

async def encerrar_wl_channel(channel: discord.TextChannel, motivo: str, delete_after: int = 20):
    try:
        await channel.send(f"🔒 **WL encerrada.** Motivo: {motivo}\n🧹 Apagando em **{delete_after}s**.")
    except Exception:
        pass
    await asyncio.sleep(delete_after)
    try:
        await channel.delete(reason=f"WL encerrada: {motivo}")
    except Exception:
        pass

class WLUserControlsView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Cancelar WL", emoji="🛑", style=discord.ButtonStyle.danger, custom_id="nr_wl_cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id and not is_staff(interaction.user):
            await interaction.response.send_message("❌ Você não pode cancelar a WL de outra pessoa.", ephemeral=True)
            return
        await interaction.response.send_message("✅ WL cancelada. Fechando canal...", ephemeral=True)
        await encerrar_wl_channel(interaction.channel, "WL cancelada pelo usuário.")

# =========================================================
# WL: STAFF REVIEW
# =========================================================
class WLStaffReviewView(discord.ui.View):
    def __init__(self, user_id: int, cidade_id: str, personagem: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.cidade_id = cidade_id
        self.personagem = personagem
        self.status = "PENDENTE"
        self.motivo: Optional[str] = None

    def _ensure_staff(self, interaction: discord.Interaction) -> bool:
        return is_staff(interaction.user)

    def _toggle_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "nr_wl_publicar_aprovada":
                    item.disabled = (self.status != "APROVADA")
                if item.custom_id == "nr_wl_publicar_reprovada":
                    item.disabled = (self.status != "REPROVADA")

    def _set_status_line(self, embed: discord.Embed):
        desc = embed.description or ""
        lines = desc.split("\n")
        if not lines:
            return
        if self.status == "PENDENTE":
            lines[0] = "**Status:** 🟣 PENDENTE"
        elif self.status == "APROVADA":
            lines[0] = "**Status:** 🟢 APROVADA (aguardando lançamento)"
        else:
            lines[0] = "**Status:** 🔴 REPROVADA (aguardando lançamento)"
        embed.description = "\n".join(lines)

    def _public_embed(self, final: str) -> discord.Embed:
        if final == "APROVADA":
            status_txt = "✅ APROVADA"
            color = VERDE
        else:
            status_txt = "❌ REPROVADA"
            color = VERMELHO

        e = discord.Embed(
            title="📌 Resultado da Whitelist",
            description=(
                f"**Status:** {status_txt}\n"
                f"**Personagem:** `{self.personagem}`\n"
                f"**ID Cidade:** `{self.cidade_id}`\n"
                f"**Discord ID:** `{self.user_id}`"
            ),
            color=color
        )
        if final == "REPROVADA" and self.motivo:
            e.add_field(name="Motivo", value=self.motivo[:1024], inline=False)
        e.set_thumbnail(url=LOGO)
        return e

    async def _apply_cidadao_and_nick(self, guild: discord.Guild) -> tuple[bool, str]:
        membro = guild.get_member(self.user_id)
        if membro is None:
            try:
                membro = await guild.fetch_member(self.user_id)
            except Exception:
                return (False, "Não consegui encontrar o membro no servidor.")

        cargo = discord.utils.get(guild.roles, name=CARGO_CIDADAO)
        if cargo is None:
            return (False, f"Cargo **{CARGO_CIDADAO}** não encontrado.")

        try:
            await membro.add_roles(cargo, reason="WL aprovada")
        except discord.Forbidden:
            return (False, "Sem permissão para setar cargos.")
        except Exception as e:
            return (False, f"Erro ao setar cargo: {repr(e)}")

        try:
            await membro.edit(nick=f"{self.personagem} - {self.cidade_id}", reason="WL aprovada")
        except discord.Forbidden:
            return (True, "Cargo setado ✅ | Nick não alterado (sem permissão).")
        except Exception:
            return (True, "Cargo setado ✅ | Nick não alterado (erro).")

        return (True, "Cargo setado ✅ | Nick alterado ✅")

    @discord.ui.button(label="Marcar Aprovada", emoji="✅", style=discord.ButtonStyle.green, custom_id="nr_wl_marcar_aprovada")
    async def marcar_aprovada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self._ensure_staff(interaction):
            await interaction.followup.send("❌ Apenas staff.", ephemeral=True)
            return
        self.status = "APROVADA"
        self._toggle_buttons()
        embed = interaction.message.embeds[0]
        self._set_status_line(embed)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("✅ Marcada como APROVADA. Publique depois de aprovar na cidade.", ephemeral=True)

    @discord.ui.button(label="Marcar Reprovada", emoji="❌", style=discord.ButtonStyle.red, custom_id="nr_wl_marcar_reprovada")
    async def marcar_reprovada(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._ensure_staff(interaction):
            await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)
            return

        class MotivoModal(discord.ui.Modal, title="Reprovar WL"):
            def __init__(self, parent: "WLStaffReviewView"):
                super().__init__(timeout=None)
                self.parent = parent
                self.motivo = discord.ui.TextInput(
                    label="Motivo (curto e claro)",
                    style=discord.TextStyle.paragraph,
                    max_length=300,
                    required=True
                )
                self.add_item(self.motivo)

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                self.parent.status = "REPROVADA"
                self.parent.motivo = self.motivo.value
                self.parent._toggle_buttons()

                embed = modal_interaction.message.embeds[0]
                self.parent._set_status_line(embed)

                found = False
                for i, f in enumerate(embed.fields):
                    if f.name == "Motivo (Staff)":
                        embed.set_field_at(i, name="Motivo (Staff)", value=self.parent.motivo[:1024], inline=False)
                        found = True
                        break
                if not found:
                    embed.add_field(name="Motivo (Staff)", value=self.parent.motivo[:1024], inline=False)

                await modal_interaction.message.edit(embed=embed, view=self.parent)
                await modal_interaction.followup.send("✅ Marcada como REPROVADA. Agora publique.", ephemeral=True)

        await interaction.response.send_modal(MotivoModal(self))

    @discord.ui.button(label="Publicar ✅", emoji="🚀", style=discord.ButtonStyle.blurple, custom_id="nr_wl_publicar_aprovada", disabled=True)
    async def publicar_aprovada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self._ensure_staff(interaction):
            await interaction.followup.send("❌ Apenas staff.", ephemeral=True)
            return
        if self.status != "APROVADA":
            await interaction.followup.send("⚠️ Marque como APROVADA primeiro.", ephemeral=True)
            return

        ch = get_wl_aprovadas_channel(interaction.guild)
        if not ch:
            await interaction.followup.send(f"❌ Crie o canal #{CANAL_WL_APROVADAS}.", ephemeral=True)
            return

        await ch.send(embed=self._public_embed("APROVADA"))
        ok, msg = await self._apply_cidadao_and_nick(interaction.guild)

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send(f"✅ Publicado em aprovadas.\n{msg}", ephemeral=True)

    @discord.ui.button(label="Publicar ❌", emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="nr_wl_publicar_reprovada", disabled=True)
    async def publicar_reprovada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not self._ensure_staff(interaction):
            await interaction.followup.send("❌ Apenas staff.", ephemeral=True)
            return
        if self.status != "REPROVADA":
            await interaction.followup.send("⚠️ Marque como REPROVADA primeiro.", ephemeral=True)
            return

        ch = get_wl_reprovadas_channel(interaction.guild)
        if not ch:
            await interaction.followup.send(f"❌ Crie o canal #{CANAL_WL_REPROVADAS}.", ephemeral=True)
            return

        await ch.send(embed=self._public_embed("REPROVADA"))

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        await interaction.followup.send("✅ Publicado em reprovadas.", ephemeral=True)

# =========================================================
# WL FLOW: SUAS 11 PERGUNTAS
# =========================================================
async def run_wl_flow_in_channel(bot: commands.Bot, channel: discord.TextChannel, user: discord.Member):
    if channel.id in ACTIVE_WL:
        return
    ACTIVE_WL.add(channel.id)

    def check(m: discord.Message):
        return m.author.id == user.id and m.channel.id == channel.id

    answers: dict[str, str] = {}
    last_question_msg: Optional[discord.Message] = None

    async def send_question_embed(title: str, desc: str):
        nonlocal last_question_msg
        if last_question_msg:
            try:
                await last_question_msg.delete()
            except Exception:
                pass

        e = discord.Embed(title=title, description=desc, color=ROXO)
        e.set_thumbnail(url=LOGO)
        e.set_footer(text="New Republic Roleplay • WL")
        last_question_msg = await channel.send(embed=e, view=WLUserControlsView(user_id=user.id))

    async def ask(question: str) -> Optional[str]:
        await send_question_embed(
            "📝 Whitelist — New Republic",
            f"**Pergunta:**\n{question}\n\n⏳ Você tem **{TEMPO_WL_POR_PERGUNTA // 60} minutos**."
        )
        try:
            msg = await bot.wait_for("message", check=check, timeout=TEMPO_WL_POR_PERGUNTA)
            txt = (msg.content or "").strip()
            try:
                await msg.delete()
            except Exception:
                pass
            return txt if txt else None
        except asyncio.TimeoutError:
            return None

    async def ask_mc(title: str, options: list[str]) -> Optional[str]:
        letters = ["A", "B", "C", "D"]
        desc = "\n".join([f"**{letters[i]})** {options[i]}" for i in range(len(options))])

        await send_question_embed(
            "✅ Pergunta de Marcação",
            f"**{title}**\n\n{desc}\n\nResponda com: **A, B, C ou D**\n"
            f"⏳ Você tem **{TEMPO_WL_POR_PERGUNTA // 60} minutos**."
        )
        try:
            msg = await bot.wait_for("message", check=check, timeout=TEMPO_WL_POR_PERGUNTA)
            ans = (msg.content or "").strip().upper()
            try:
                await msg.delete()
            except Exception:
                pass
            if ans in letters[:len(options)]:
                return f"{ans}) {options[letters.index(ans)]}"
            return None
        except asyncio.TimeoutError:
            return None

    try:
        r = await ask("Qual seu ID?")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["ID"] = r

        r = await ask("Qual nome e sobrenome do seu personagem?")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Personagem"] = r

        r = await ask("Qual idade do seu personagem?")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Idade Personagem"] = r

        r = await ask("Qual sua idade real?")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Idade Real"] = r

        r = await ask("Para você o que é Hard Roleplay?")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Hard Roleplay"] = r

        r = await ask("É permitido usar conhecimento de fora no jogo (ex: conhecimentos mecânicos)? Explique sua resposta.")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Conhecimento de Fora"] = r

        r = await ask_mc("Em qual quebra de regra o RDM e VDM se encaixa?", [
            "Atirar em alguém sem motivo.",
            "Atropelar propositalmente.",
            "Anti-RP.",
            "Nenhuma das opções."
        ])
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["RDM/VDM"] = r

        r = await ask_mc("O que é o Fear RP?", [
            "Medo de morrer e se machucar.",
            "Roleplay de preconceito.",
            "Medo do que pode acontecer de ruim com o personagem.",
            "Roleplay de bulling."
        ])
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Fear RP"] = r

        r = await ask_mc("Qual dessas irregularidades quebra a regra de desenvolvimento do personagem?", [
            "Realizar um corte de cabelo sem narrativa.",
            "Assaltar um caixa eletrônico usando o veículo do táxi.",
            "Assaltar um caixa eletrônico usando uma Ferrari.",
            "Nenhuma das alternativas acima."
        ])
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Desenvolvimento"] = r

        r = await ask_mc("Quais são as safe zones?", [
            "Apenas hospital.",
            "Mecânicas, garagens e empregos legais.",
            "Empregos Ilegais e Hospital.",
            "Nenhuma das alternativas acima."
        ])
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["Safe Zones"] = r

        r = await ask("Crie a história do seu personagem.")
        if not r:
            await encerrar_wl_channel(channel, "Tempo esgotado ou resposta inválida.")
            return
        answers["História"] = r

        staff_channel = get_wl_staff_channel(channel.guild)
        if not staff_channel:
            await encerrar_wl_channel(channel, f"Canal #{CANAL_WL_STAFF} não encontrado.")
            return

        embed_staff = discord.Embed(
            title="📝 Whitelist Recebida",
            description=(
                f"**Status:** 🟣 PENDENTE\n"
                f"**Usuário:** {user.mention}\n"
                f"**Discord ID:** `{user.id}`\n"
                f"**ID:** `{answers['ID']}`\n"
                f"**Personagem:** `{answers['Personagem']}`"
            ),
            color=ROXO
        )
        embed_staff.add_field(name="Idade (Personagem)", value=answers["Idade Personagem"][:1024], inline=True)
        embed_staff.add_field(name="Idade (Real)", value=answers["Idade Real"][:1024], inline=True)
        embed_staff.add_field(name="Hard Roleplay", value=answers["Hard Roleplay"][:1024], inline=False)
        embed_staff.add_field(name="Conhecimento de Fora", value=answers["Conhecimento de Fora"][:1024], inline=False)
        embed_staff.add_field(name="RDM/VDM", value=answers["RDM/VDM"][:1024], inline=True)
        embed_staff.add_field(name="Fear RP", value=answers["Fear RP"][:1024], inline=True)
        embed_staff.add_field(name="Desenvolvimento", value=answers["Desenvolvimento"][:1024], inline=False)
        embed_staff.add_field(name="Safe Zones", value=answers["Safe Zones"][:1024], inline=False)
        embed_staff.add_field(name="História", value=answers["História"][:1024], inline=False)
        embed_staff.set_thumbnail(url=LOGO)

        await staff_channel.send(
            embed=embed_staff,
            view=WLStaffReviewView(user_id=user.id, cidade_id=answers["ID"], personagem=answers["Personagem"])
        )

        await encerrar_wl_channel(channel, "WL enviada para análise da staff.")
        return

    finally:
        ACTIVE_WL.discard(channel.id)

# =========================================================
# WL: VIEW "Começar"
# =========================================================
class WLIniciarNoCanalView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Começar Perguntas", emoji="🚀", style=discord.ButtonStyle.green, custom_id="nr_wl_comecar")
    async def comecar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono da WL pode iniciar.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Iniciando perguntas...", ephemeral=True)

        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await run_wl_flow_in_channel(interaction.client, interaction.channel, interaction.user)

# =========================================================
# WL: PAINEL PÚBLICO + LOCK
# =========================================================
class WLPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Iniciar WL", emoji="📝", style=discord.ButtonStyle.green, custom_id="nr_wl_iniciar")
    async def iniciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        if is_wl_locked():
            await interaction.followup.send("🔒 WL TRANCADA no momento. Aguarde a staff.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        categoria = discord.utils.get(guild.categories, name=CATEGORIA_WL)
        if not categoria:
            try:
                categoria = await guild.create_category(CATEGORIA_WL)
            except discord.Forbidden:
                await interaction.followup.send("❌ Sem permissão para criar a categoria WHITELIST.", ephemeral=True)
                return

        staff_role = discord.utils.get(guild.roles, name=CARGO_STAFF)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = user.name.lower().replace(" ", "-")
        existing = discord.utils.get(categoria.text_channels, name=f"wl-{safe_name}")
        if existing:
            await interaction.followup.send(f"⚠️ Você já tem uma WL aberta: {existing.mention}", ephemeral=True)
            return

        try:
            wl_channel = await guild.create_text_channel(name=f"wl-{safe_name}", category=categoria, overwrites=overwrites)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sem permissão para criar canal WL.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Sua WL foi criada: {wl_channel.mention}", ephemeral=True)

        embed = discord.Embed(
            title="📝 Whitelist — New Republic",
            description=(
                f"{user.mention}, bem-vindo(a)!\n\n"
                "Você vai responder **pergunta por pergunta**.\n"
                f"⏳ **{TEMPO_WL_POR_PERGUNTA // 60} min por pergunta**.\n\n"
                "Clique em **Começar Perguntas**."
            ),
            color=ROXO
        )
        embed.set_thumbnail(url=LOGO)

        await wl_channel.send(embed=embed, view=WLIniciarNoCanalView(user_id=user.id))

    @discord.ui.button(label="Travar/Destravar WL", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="nr_wl_toggle_lock")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)
            return

        locked = is_wl_locked()
        set_wl_locked(not locked)
        now_locked = not locked

        # ✅ Atualiza o painel (embed) na mesma mensagem
        try:
            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0]
                status = "🔒 TRANCADA" if now_locked else "✅ ABERTA"
                embed.description = (
                    f"Status da WL: **{status}**\n\n"
                    "Clique para iniciar sua WL.\n"
                    f"⏳ **{TEMPO_WL_POR_PERGUNTA // 60} min por pergunta**."
                )
                await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

        state = "TRANCADA 🔒" if now_locked else "DESTRANCADA ✅"
        await interaction.response.send_message(f"✅ WL agora está: **{state}**", ephemeral=True)

# =========================================================
# BOT
# =========================================================
class NewRepublicBOT(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="nr", intents=intents)

    async def setup_hook(self):
        self.add_view(VerificarView())
        self.add_view(TicketPanel())
        self.add_view(TicketControls())
        self.add_view(WLPanelView())

        # Sync
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

bot = NewRepublicBOT()

# =========================================================
# SLASH COMMANDS
# =========================================================
@bot.tree.command(name="painel_registro", description="Envia o painel de verificação/registro")
async def painel_registro(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 Verificação • New Republic",
        description=(
            "Bem-vindo(a)!\n\n"
            "✅ **Como entrar:**\n"
            "1) Clique em **Registrar-se**\n"
            "2) Você recebe o cargo da cidade\n"
            "3) Acesso liberado nas áreas do servidor\n\n"
            "⚠️ Se o botão não funcionar, chame um staff."
        ),
        color=ROXO
    )
    embed.add_field(name="📌 Importante", value="Mantenha seu Discord organizado e respeite as regras.", inline=False)
    embed.set_thumbnail(url=LOGO)
    await interaction.response.send_message("✅ Painel enviado.", ephemeral=True)
    await interaction.channel.send(embed=embed, view=VerificarView())

@bot.tree.command(name="ticket_painel", description="Envia o painel da central de tickets")
async def ticket_painel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description=(
            "Selecione abaixo o **tipo de atendimento**.\n\n"
            "🟡 Ao abrir, o ticket fica **aguardando staff**.\n"
            "🟢 Quando um staff assumir, o canal muda de nome automaticamente."
        ),
        color=0x5865F2
    )
    embed.add_field(name="⏱️ Dica", value="Explique o assunto com detalhes para agilizar.", inline=False)
    embed.set_thumbnail(url=LOGO)
    await interaction.response.send_message("✅ Painel enviado.", ephemeral=True)
    await interaction.channel.send(embed=embed, view=TicketPanel())

@bot.tree.command(name="anunciar", description="Enviar anúncio em embed (somente staff/admin)")
@app_commands.checks.has_permissions(manage_messages=True)
async def anunciar(interaction: discord.Interaction, titulo: str, mensagem: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(embed=build_announcement_embed(titulo, mensagem))
    await interaction.followup.send("✅ Anúncio enviado.", ephemeral=True)

@bot.tree.command(name="wl_painel", description="Envia o painel para iniciar a whitelist")
async def wl_painel(interaction: discord.Interaction):
    locked = is_wl_locked()
    status = "🔒 TRANCADA" if locked else "✅ ABERTA"

    embed = discord.Embed(
        title="📝 Whitelist — New Republic",
        description=(
            f"Status da WL: **{status}**\n\n"
            "Clique para iniciar sua WL.\n"
            f"⏳ **{TEMPO_WL_POR_PERGUNTA // 60} min por pergunta**."
        ),
        color=ROXO
    )
    embed.set_thumbnail(url=LOGO)
    await interaction.response.send_message("✅ Painel de WL enviado.", ephemeral=True)
    await interaction.channel.send(embed=embed, view=WLPanelView())

# =========================================================
# CHANGELOG: /log (abre modal, envia no mesmo canal)
# =========================================================
class LogModal(discord.ui.Modal, title="📌 Nova Change Log — New Republic"):
    versao = discord.ui.TextInput(
        label="Versão (ex: v1.9.1)",
        placeholder="v1.9.1",
        max_length=20,
        required=True
    )
    titulo = discord.ui.TextInput(
        label="Título (ex: Ajustes no Ticket)",
        placeholder="Ajustes no Ticket",
        max_length=60,
        required=True
    )
    mudancas = discord.ui.TextInput(
        label="Mudanças (pode usar ✅ 🔧 🧠 etc)",
        placeholder="✅ ...\n🔧 ...\n🧠 ...",
        style=discord.TextStyle.paragraph,
        max_length=1700,
        required=True
    )
    observacoes = discord.ui.TextInput(
        label="Observações (opcional)",
        placeholder="Ex: Pequenas otimizações e correções",
        style=discord.TextStyle.paragraph,
        max_length=700,
        required=False
    )

    def __init__(self, author: discord.Member):
        super().__init__()
        self.author = author

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        if channel is None:
            await interaction.response.send_message("❌ Não consegui identificar o canal.", ephemeral=True)
            return

        v = norm(str(self.versao.value))
        t = norm(str(self.titulo.value))
        m = norm(str(self.mudancas.value))
        o = norm(str(self.observacoes.value)) if self.observacoes.value else ""

        desc = f"**{t}**\n \n\n{m}"
        if o:
            desc += f"\n \n\n**Observações:**\n{o}"

        embed = discord.Embed(
            title=f"📌 Change Log {v}",
            description=desc,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Publicado por {self.author.display_name}")

        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Changelog enviada neste canal!", ephemeral=True)

@bot.tree.command(name="log", description="Criar uma Change Log (abre um painel).")
@app_commands.checks.has_permissions(manage_guild=True)
async def log(interaction: discord.Interaction):
    await interaction.response.send_modal(LogModal(interaction.user))

# =========================================================
# START
# =========================================================
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não encontrado no Render.")
bot.run(TOKEN)