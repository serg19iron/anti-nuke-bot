import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Загружаем токен из файла .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DEBUG_CHANNEL_ID = 1511315014038847588
ALERT_CHANNEL_ID = 1511315091738595390
FREEZE_ROLE_ID = 1511315123430621214

ALLOWED_COMMAND_ROLES = [1403302279863599134, 1139227086360420392] 

class Config:
    ACTION_LIMIT_MODIFY = 3
    ACTION_LIMIT_CREATE = 5
    TIME_WINDOW = 60
    WARNING_TIME = 60
    DAYS_OLD_LIMIT = 3
    WHITELIST = set() 

tracker = {}
warnings = {}
saved_roles = {} 

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

def get_settings_embed():
    wl_text = ", ".join([f"<@{uid}>" for uid in Config.WHITELIST]) if Config.WHITELIST else "Пусто"
    
    embed = discord.Embed(title="⚙️ Панель управления Anti-Nuke", color=discord.Color.purple())
    embed.add_field(name="Лимит изменения (Старые/Новые)", value=f"{Config.ACTION_LIMIT_MODIFY} шт.", inline=True)
    embed.add_field(name="Лимит создания", value=f"{Config.ACTION_LIMIT_CREATE} шт.", inline=True)
    embed.add_field(name="Окно времени", value=f"{Config.TIME_WINDOW} сек.", inline=True)
    embed.add_field(name="Время 'Оранжевой метки'", value=f"{Config.WARNING_TIME} сек.", inline=True)
    embed.add_field(name="Возраст 'Старого' канала", value=f"{Config.DAYS_OLD_LIMIT} дн.", inline=True)
    embed.add_field(name="🛡️ Белый список (Игнорируются)", value=wl_text, inline=False)
    return embed

class SettingsModal(discord.ui.Modal, title='Настройка параметров'):
    inp_modify = discord.ui.TextInput(label='Лимит Изменения/Удаления', default=str(Config.ACTION_LIMIT_MODIFY))
    inp_create = discord.ui.TextInput(label='Лимит Создания', default=str(Config.ACTION_LIMIT_CREATE))
    inp_window = discord.ui.TextInput(label='Окно времени (секунды)', default=str(Config.TIME_WINDOW))
    inp_warning = discord.ui.TextInput(label='Время метки (секунды)', default=str(Config.WARNING_TIME))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            Config.ACTION_LIMIT_MODIFY = int(self.inp_modify.value)
            Config.ACTION_LIMIT_CREATE = int(self.inp_create.value)
            Config.TIME_WINDOW = int(self.inp_window.value)
            Config.WARNING_TIME = int(self.inp_warning.value)
            await interaction.response.edit_message(embed=get_settings_embed(), view=SettingsView())
        except ValueError:
            await interaction.response.send_message("❌ Ошибка: Вводите только числа!", ephemeral=True)

class WhitelistSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Выбрать пользователя/бота (Вайтлист)", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        user = self.values[0]
        if user.id in Config.WHITELIST:
            Config.WHITELIST.remove(user.id)
            msg = f"❌ {user.mention} удален из Белого списка."
        else:
            Config.WHITELIST.add(user.id)
            msg = f"✅ {user.mention} добавлен в Белый список."
            
        await interaction.response.edit_message(embed=get_settings_embed(), view=SettingsView())
        await interaction.followup.send(msg, ephemeral=True)

class SettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WhitelistSelect())

    @discord.ui.button(label="📝 Изменить лимиты", style=discord.ButtonStyle.primary, row=1)
    async def edit_limits(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsModal())

@bot.tree.command(name="anti-crasher", description="Открыть панель настройки защиты")
async def anti_crasher_cmd(interaction: discord.Interaction):
    has_role = any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles)
    if not has_role and interaction.user != interaction.guild.owner:
        return await interaction.response.send_message("❌ У вас нет прав для использования этой команды.", ephemeral=True)
    
    await interaction.response.send_message(embed=get_settings_embed(), view=SettingsView(), ephemeral=True)

class ActionButtons(discord.ui.View):
    def __init__(self, target_member: discord.Member):
        super().__init__(timeout=None)
        self.target_member = target_member

    @discord.ui.button(label="❄️ Заморозить", style=discord.ButtonStyle.danger)
    async def freeze_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await apply_freeze(interaction.guild, self.target_member)
        if self.target_member.id in warnings: del warnings[self.target_member.id]
        await interaction.response.send_message(f"🚨 {self.target_member.mention} заморожен админом {interaction.user.mention}.", ephemeral=False)
        self.stop()

    @discord.ui.button(label="🛡️ Снять все роли", style=discord.ButtonStyle.primary)
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
        
        await interaction.response.send_message(f"✅ {self.target_member.mention} оправдан! Роли возвращены, заморозка снята.", ephemeral=False)
        self.stop()

async def apply_freeze(guild, member):
    if member == guild.owner: return
    
    await strip_all_roles(guild, member)
    
    freeze_role = guild.get_role(FREEZE_ROLE_ID)
    if freeze_role:
        try: await member.add_roles(freeze_role, reason="Anti-Nuke: Авто-заморозка")
        except: pass

async def strip_all_roles(guild, member):
    if member == guild.owner: return
    
    roles_to_remove = []
    if member.id not in saved_roles:
        saved_roles[member.id] = []
        
    for role in member.roles:
        if role == guild.default_role: continue 
        if role >= guild.me.top_role: continue  
        if role.managed: continue               
            
        roles_to_remove.append(role)
        if role.id not in saved_roles[member.id]:
            saved_roles[member.id].append(role.id)
            
    if roles_to_remove:
        try: await member.remove_roles(*roles_to_remove, reason="Anti-Nuke: Защита")
        except: pass

async def restore_roles(guild, member):
    """Снимает заморозку и возвращает ранее сохраненные роли"""
    freeze_role = guild.get_role(FREEZE_ROLE_ID)
    if freeze_role and freeze_role in member.roles:
        try: await member.remove_roles(freeze_role, reason="Anti-Nuke: Оправдан")
        except: pass

    if member.id in saved_roles:
        roles_to_add = []
        for role_id in saved_roles[member.id]:
            role = guild.get_role(role_id)
            if role and role < guild.me.top_role: 
                roles_to_add.append(role)
                
        if roles_to_add:
            try: await member.add_roles(*roles_to_add, reason="Anti-Nuke: Возврат ролей (Оправдан)")
            except: pass
            
        del saved_roles[member.id]


def add_action_to_tracker(user_id, list_type):
    now = datetime.now(timezone.utc)
    if user_id not in tracker: tracker[user_id] = {'old': [], 'new': [], 'create': []}
    tracker[user_id][list_type].append(now)
    tracker[user_id][list_type] = [t for t in tracker[user_id][list_type] if (now - t).total_seconds() < Config.TIME_WINDOW]
    return len(tracker[user_id][list_type])


async def process_channel_action(channel, action_type):
    guild = channel.guild
    now = datetime.now(timezone.utc)
    
    if action_type == 'create':
        list_type, current_limit, status_text = 'create', Config.ACTION_LIMIT_CREATE, "Создание"
    else:
        is_old = (now - channel.created_at).days > Config.DAYS_OLD_LIMIT
        list_type, current_limit = ('old', Config.ACTION_LIMIT_MODIFY) if is_old else ('new', Config.ACTION_LIMIT_MODIFY)
        status_text = 'Старый' if is_old else 'Новый'

    await discord.utils.sleep_until(now + timedelta(seconds=1))
    audit_action = discord.AuditLogAction.channel_delete if action_type == 'delete' else discord.AuditLogAction.channel_create if action_type == 'create' else discord.AuditLogAction.channel_update
    
    user_info = None
    async for entry in guild.audit_logs(action=audit_action, limit=1):
        if entry.target.id == channel.id:
            user_info = entry.user
            break
            
    if not user_info: return
    
    if user_info.id == bot.user.id: return 

    member = guild.get_member(user_info.id)
    if not member: return 

    if member.id in Config.WHITELIST: return 

    debug_channel = guild.get_channel(DEBUG_CHANNEL_ID)
    alert_channel = guild.get_channel(ALERT_CHANNEL_ID)

    if member.id in warnings:
        if (now - warnings[member.id]).total_seconds() <= Config.WARNING_TIME:
            del warnings[member.id]
            tracker[member.id] = {'old': [], 'new': [], 'create': []}
            await apply_freeze(guild, member)
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="🚨 АВТО-ЗАМОРОЗКА 🚨", description=f"{member.mention} продолжил атаку! Все роли сняты, выдана заморозка.", color=discord.Color.dark_red()))
            return
        else:
            del warnings[member.id]

    action_count = add_action_to_tracker(member.id, list_type)
    
    if debug_channel:
        is_bot_text = "🤖 БОТ/ПРИЛОЖЕНИЕ" if member.bot else "👤 Человек"
        await debug_channel.send(embed=discord.Embed(title="🛠️ Действие с каналом", description=f"Кто: {member.mention} ({is_bot_text})\nКанал: {channel.name} ({status_text})", color=discord.Color.blue()).set_footer(text=f"Счетчик: {action_count}/{current_limit}"))

    if action_count >= current_limit:
        if list_type == 'old':
            await apply_freeze(guild, member)
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="🚨 АТАКА НА СТАРЫЕ КАНАЛЫ 🚨", description=f"{member.mention} заморожен. Все роли сняты.", color=discord.Color.red()), view=ActionButtons(member))
        else:
            warnings[member.id] = now
            if alert_channel: await alert_channel.send(embed=discord.Embed(title="⚠️ ПОДОЗРИТЕЛЬНАЯ АКТИВНОСТЬ ⚠️", description=f"{member.mention} превысил лимиты. Ждем {Config.WARNING_TIME} сек.", color=discord.Color.orange()), view=ActionButtons(member))
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