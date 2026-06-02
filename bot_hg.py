import discord
from discord.ext import commands
import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Загрузка токена
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# ==========================================
# МЕНЕДЖЕР КОНФИГУРАЦИИ (СОХРАНЕНИЕ В JSON)
# ==========================================
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "ACTION_LIMIT_MODIFY": 3,
    "ACTION_LIMIT_CREATE": 5,
    "TIME_WINDOW": 60,
    "WARNING_TIME": 60,
    "DAYS_OLD_LIMIT": 3,
    "WHITELIST": [],
    "ALLOWED_COMMAND_ROLES": [],
    "DEBUG_CHANNEL_ID": None,
    "ALERT_CHANNEL_ID": None,
    "FREEZE_ROLE_ID": None
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Добавляем новые ключи, если они появились в обновлении кода
            for k, v in DEFAULT_CONFIG.items():
                if k not in data: data[k] = v
            return data
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

config = load_config()

# Память бота (очищается при перезапуске)
tracker = {}
warnings = {}
saved_roles = {} 

# ==========================================
# ОСНОВНОЙ КЛАСС БОТА
# ==========================================
class AntiNukeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        await self.tree.sync()
        print(f'✅ Бот {self.user} запущен! Защита активна.')

bot = AntiNukeBot()

# ==========================================
# UI / ГРАФИЧЕСКИЙ ИНТЕРФЕЙС НАСТРОЕК
# ==========================================
def get_dashboard_embed():
    """Генерирует красивую главную панель управления"""
    embed = discord.Embed(title="🛡️ Панель управления Anti-Nuke", color=discord.Color.from_rgb(43, 45, 49))
    embed.description = "Добро пожаловать в систему защиты сервера.\nВыберите категорию настроек с помощью кнопок ниже."
    
    # Секция Лимитов
    limits_text = (
        f"**Изменения:** {config['ACTION_LIMIT_MODIFY']} шт.\n"
        f"**Создания:** {config['ACTION_LIMIT_CREATE']} шт.\n"
        f"**Окно времени:** {config['TIME_WINDOW']} сек.\n"
        f"**Таймер метки:** {config['WARNING_TIME']} сек.\n"
        f"**Старый канал от:** {config['DAYS_OLD_LIMIT']} дн."
    )
    embed.add_field(name="📊 Текущие лимиты", value=limits_text, inline=True)

    # Секция Каналов
    alert_ch = f"<#{config['ALERT_CHANNEL_ID']}>" if config['ALERT_CHANNEL_ID'] else "🔴 Не задан"
    debug_ch = f"<#{config['DEBUG_CHANNEL_ID']}>" if config['DEBUG_CHANNEL_ID'] else "🔴 Не задан"
    channels_text = f"**Тревога (Alerts):** {alert_ch}\n**Логи (Debug):** {debug_ch}"
    embed.add_field(name="💬 Каналы вывода", value=channels_text, inline=True)

    embed.add_field(name="\u200b", value="\u200b", inline=False) # Разделитель

    # Секция Ролей
    freeze_rl = f"<@&{config['FREEZE_ROLE_ID']}>" if config['FREEZE_ROLE_ID'] else "🔴 Не задана"
    admins_rl = ", ".join([f"<@&{r}>" for r in config['ALLOWED_COMMAND_ROLES']]) if config['ALLOWED_COMMAND_ROLES'] else "🟡 Только Владелец"
    roles_text = f"**Роль Заморозки:** {freeze_rl}\n**Доступ к панели:** {admins_rl}"
    embed.add_field(name="🎭 Роли и Доступы", value=roles_text, inline=True)

    # Секция Вайтлиста
    wl_text = ", ".join([f"<@{uid}>" for uid in config['WHITELIST']]) if config['WHITELIST'] else "⚪ Пусто"
    embed.add_field(name="🛡️ Белый список (Игнор)", value=wl_text, inline=True)
    
    embed.set_footer(text=f"AntiNuke System • Последнее обновление: {datetime.now().strftime('%H:%M:%S')}")
    return embed

# --- МОДАЛЬНОЕ ОКНО ЛИМИТОВ ---
class SettingsModal(discord.ui.Modal, title='Настройка лимитов'):
    inp_modify = discord.ui.TextInput(label='Лимит Изменений/Удалений', default=str(config['ACTION_LIMIT_MODIFY']))
    inp_create = discord.ui.TextInput(label='Лимит Создания', default=str(config['ACTION_LIMIT_CREATE']))
    inp_window = discord.ui.TextInput(label='Окно времени (секунды)', default=str(config['TIME_WINDOW']))
    inp_warning = discord.ui.TextInput(label='Время желтой метки (сек)', default=str(config['WARNING_TIME']))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config['ACTION_LIMIT_MODIFY'] = int(self.inp_modify.value)
            config['ACTION_LIMIT_CREATE'] = int(self.inp_create.value)
            config['TIME_WINDOW'] = int(self.inp_window.value)
            config['WARNING_TIME'] = int(self.inp_warning.value)
            save_config(config)
            await interaction.response.edit_message(embed=get_dashboard_embed(), view=MainDashboardView())
        except ValueError:
            await interaction.response.send_message("❌ Ошибка: Вводите только числа!", ephemeral=True)

# --- МЕНЮ ВЫБОРА КАНАЛОВ ---
class ChannelsMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Выберите канал для ТРЕВОГИ (Alerts)")
    async def select_alert(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        config['ALERT_CHANNEL_ID'] = select.values[0].id
        save_config(config)
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=self)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Выберите канал для ЛОГОВ (Debug)")
    async def select_debug(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        config['DEBUG_CHANNEL_ID'] = select.values[0].id
        save_config(config)
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=self)

    @discord.ui.button(label="⬅️ Назад", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=MainDashboardView())

# --- МЕНЮ ВЫБОРА РОЛЕЙ ---
class RolesMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Выберите роль для ЗАМОРОЗКИ нарушителя")
    async def select_freeze(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        config['FREEZE_ROLE_ID'] = select.values[0].id
        save_config(config)
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роль для доступа к этой панели (Можно выбрать несколько)", max_values=3)
    async def select_admins(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        config['ALLOWED_COMMAND_ROLES'] = [role.id for role in select.values]
        save_config(config)
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=self)

    @discord.ui.button(label="⬅️ Назад", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=MainDashboardView())

# --- МЕНЮ ВАЙТЛИСТА ---
class WhitelistMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Добавить/Удалить пользователя из Вайтлиста")
    async def select_wl(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        user_id = select.values[0].id
        if user_id in config['WHITELIST']:
            config['WHITELIST'].remove(user_id)
            msg = f"❌ {select.values[0].mention} удален из Белого списка."
        else:
            config['WHITELIST'].append(user_id)
            msg = f"✅ {select.values[0].mention} добавлен в Белый список."
        save_config(config)
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=self)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="⬅️ Назад", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=get_dashboard_embed(), view=MainDashboardView())

# --- ГЛАВНОЕ МЕНЮ (НАВИГАЦИЯ) ---
class MainDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Лимиты", style=discord.ButtonStyle.primary, custom_id="btn_limits")
    async def limits_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsModal())

    @discord.ui.button(label="💬 Каналы", style=discord.ButtonStyle.secondary, custom_id="btn_channels")
    async def channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=ChannelsMenu())

    @discord.ui.button(label="🎭 Роли", style=discord.ButtonStyle.secondary, custom_id="btn_roles")
    async def roles_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=RolesMenu())

    @discord.ui.button(label="🛡️ Вайтлист", style=discord.ButtonStyle.success, custom_id="btn_wl")
    async def wl_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=WhitelistMenu())


# ==========================================
# КОМАНДА ВЫЗОВА ПАНЕЛИ
# ==========================================
@bot.tree.command(name="anti-crasher", description="Открыть панель настройки защиты")
async def anti_crasher_cmd(interaction: discord.Interaction):
    # Проверка прав: Либо владелец сервера, либо имеет разрешенную роль
    has_role = any(role.id in config['ALLOWED_COMMAND_ROLES'] for role in interaction.user.roles)
    if not has_role and interaction.user != interaction.guild.owner:
        return await interaction.response.send_message("❌ У вас нет прав для использования этой команды.", ephemeral=True)
    
    await interaction.response.send_message(embed=get_dashboard_embed(), view=MainDashboardView(), ephemeral=True)

# ==========================================
# ЛОГИКА ЗАЩИТЫ И КНОПОК НАКАЗАНИЯ
# ==========================================
class ActionButtons(discord.ui.View):
    def __init__(self, target_member: discord.Member):
        super().__init__(timeout=None)
        self.target_member = target_member

    @discord.ui.button(label="❄️ Заморозить", style=discord.ButtonStyle.danger)
    async def freeze_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await apply_freeze(interaction.guild, self.target_member)
        if self.target_member.id in warnings: del warnings[self.target_member.id]
        await interaction.response.send_message(f"🚨 {self.target_member.mention} принудительно заморожен админом {interaction.user.mention}.", ephemeral=False)
        self.stop()

    @discord.ui.button(label="🛡️ Снять роли", style=discord.ButtonStyle.primary)
    async def strip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await strip_all_roles(interaction.guild, self.target_member)
        if self.target_member.id in warnings: del warnings[self.target_member.id]
        await interaction.response.send_message(f"🛡️ С {self.target_member.mention} сняты все доступные роли.", ephemeral=False)
        self.stop()

    @discord.ui.button(label="✅ Оправдать", style=discord.ButtonStyle.success)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target_member.id in tracker: del tracker[self.target_member.id]
        if self.target_member.id in warnings: del warnings[self.target_member.id]
        await restore_roles(interaction.guild, self.target_member)
        await interaction.response.send_message(f"✅ {self.target_member.mention} оправдан! Роли возвращены, метки сняты.", ephemeral=False)
        self.stop()

async def apply_freeze(guild, member):
    if member == guild.owner: return
    await strip_all_roles(guild, member)
    if config['FREEZE_ROLE_ID']:
        freeze_role = guild.get_role(config['FREEZE_ROLE_ID'])
        if freeze_role:
            try: await member.add_roles(freeze_role, reason="Anti-Nuke: Авто-заморозка")
            except: pass

async def strip_all_roles(guild, member):
    if member == guild.owner: return
    roles_to_remove = []
    if member.id not in saved_roles: saved_roles[member.id] = []
        
    for role in member.roles:
        if role == guild.default_role or role >= guild.me.top_role or role.managed: continue               
        roles_to_remove.append(role)
        if role.id not in saved_roles[member.id]:
            saved_roles[member.id].append(role.id)
            
    if roles_to_remove:
        try: await member.remove_roles(*roles_to_remove, reason="Anti-Nuke: Защита")
        except: pass

async def restore_roles(guild, member):
    if config['FREEZE_ROLE_ID']:
        freeze_role = guild.get_role(config['FREEZE_ROLE_ID'])
        if freeze_role and freeze_role in member.roles:
            try: await member.remove_roles(freeze_role, reason="Anti-Nuke: Оправдан")
            except: pass

    if member.id in saved_roles:
        roles_to_add = [guild.get_role(rid) for rid in saved_roles[member.id] if guild.get_role(rid) and guild.get_role(rid) < guild.me.top_role]
        if roles_to_add:
            try: await member.add_roles(*roles_to_add, reason="Anti-Nuke: Возврат ролей (Оправдан)")
            except: pass
        del saved_roles[member.id]

def add_action_to_tracker(user_id, list_type):
    now = datetime.now(timezone.utc)
    if user_id not in tracker: tracker[user_id] = {'old': [], 'new': [], 'create': []}
    tracker[user_id][list_type].append(now)
    tracker[user_id][list_type] = [t for t in tracker[user_id][list_type] if (now - t).total_seconds() < config['TIME_WINDOW']]
    return len(tracker[user_id][list_type])

async def process_channel_action(channel, action_type):
    guild = channel.guild
    now = datetime.now(timezone.utc)
    
    if action_type == 'create':
        list_type, current_limit, status_text = 'create', config['ACTION_LIMIT_CREATE'], "Создание"
    else:
        is_old = (now - channel.created_at).days > config['DAYS_OLD_LIMIT']
        list_type, current_limit = ('old', config['ACTION_LIMIT_MODIFY']) if is_old else ('new', config['ACTION_LIMIT_MODIFY'])
        status_text = 'Старый' if is_old else 'Новый'

    await discord.utils.sleep_until(now + timedelta(seconds=1))
    audit_action = discord.AuditLogAction.channel_delete if action_type == 'delete' else discord.AuditLogAction.channel_create if action_type == 'create' else discord.AuditLogAction.channel_update
    
    user_info = None
    async for entry in guild.audit_logs(action=audit_action, limit=1):
        if entry.target.id == channel.id:
            user_info = entry.user
            break
            
    if not user_info or user_info.id == bot.user.id: return 

    member = guild.get_member(user_info.id)
    if not member or member.id in config['WHITELIST']: return 

    debug_channel = guild.get_channel(config['DEBUG_CHANNEL_ID']) if config['DEBUG_CHANNEL_ID'] else None
    alert_channel = guild.get_channel(config['ALERT_CHANNEL_ID']) if config['ALERT_CHANNEL_ID'] else None

    if member.id in warnings:
        if (now - warnings[member.id]).total_seconds() <= config['WARNING_TIME']:
            del warnings[member.id]
            tracker[member.id] = {'old': [], 'new': [], 'create': []}
            await apply_freeze(guild, member)
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="🚨 АВТО-ЗАМОРОЗКА 🚨", description=f"{member.mention} продолжил атаку! Все роли сняты, выдана заморозка.", color=discord.Color.dark_red()))
            return
        else: del warnings[member.id]

    action_count = add_action_to_tracker(member.id, list_type)
    
    if debug_channel:
        is_bot_text = "🤖 БОТ" if member.bot else "👤 Человек"
        await debug_channel.send(embed=discord.Embed(title="🛠️ Действие с каналом", description=f"Кто: {member.mention} ({is_bot_text})\nКанал: {channel.name} ({status_text})", color=discord.Color.blue()).set_footer(text=f"Счетчик: {action_count}/{current_limit}"))

    if action_count >= current_limit:
        if list_type == 'old':
            await apply_freeze(guild, member)
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="🚨 АТАКА НА СТАРЫЕ КАНАЛЫ 🚨", description=f"{member.mention} заморожен. Все роли сняты.", color=discord.Color.red()), view=ActionButtons(member))
        else:
            warnings[member.id] = now
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="⚠️ ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ ⚠️", description=f"{member.mention} превысил лимиты. Ждем {config['WARNING_TIME']} сек.", color=discord.Color.orange()), view=ActionButtons(member))
        tracker[member.id][list_type] = []

@bot.event
async def on_guild_channel_create(channel): await process_channel_action(channel, 'create')
@bot.event
async def on_guild_channel_delete(channel): await process_channel_action(channel, 'delete')
@bot.event
async def on_guild_channel_update(before, after):
    if before.name == after.name and before.topic == after.topic and before.category == after.category and before.position == after.position: return
    await process_channel_action(after, 'update')

bot.run(TOKEN)