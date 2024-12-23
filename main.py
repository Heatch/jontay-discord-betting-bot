import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
from gambling import odds, locktime
from pymongo.mongo_client import MongoClient
from datetime import datetime, timedelta
import random

# Constants
INITIAL_BALANCE = 1000
CURRENCY_NAME = "fairydust"

# Getting environment variables
load_dotenv()
SERVER_ID = os.getenv('COVID_ID')
GUILD_ID = discord.Object(id=int(SERVER_ID))
MONGO_URI = os.getenv('uri')

# Create a new client and connect to the server
mclient = MongoClient(MONGO_URI)
db = mclient.usereconomy
users_collection = db.users
bets_collection = db.bets

# Bot initial boot up
class Client(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        self.check_lock_times.start()

    async def on_ready(self):
        print(f'Logged in as {self.user}')

        try:
            GUILD_ID = discord.Object(id=int(SERVER_ID))
            synced = await self.tree.sync(guild=GUILD_ID)
            print(f"Synced {len(synced)} commands to {GUILD_ID}")

        except Exception as e:
            print(f"Failed to sync commands: {e}")
    
    async def on_member_join(self, member):
        """When a new member joins the server, initialize their balance"""
        await ensure_user_exists(member.id)
    
    @tasks.loop(seconds=60) # Check every minute if a betting line should be locked
    async def check_lock_times(self):
        now = datetime.now()
        for bet in bets_collection.find({"locks": {"$lte": now}, "locked": False}):
            channel = self.get_channel(bet["channel_id"])
            message = await channel.fetch_message(bet["message_id"])
            new_embed = locking(message)
            await message.edit(embed=new_embed, view=None)
            bets_collection.update_one({"message_id": message.id}, {"$set": {"locked": True}})
    
    @check_lock_times.before_loop
    async def before_check_lock_times(self):
        await self.wait_until_ready()

# Intent setup
intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix='!', intents=intents)

# User economy setup

# Checking if user exists in database if not create one with initial balance
async def ensure_user_exists(user_id: int) -> dict:
    """Ensure user exists in database, create if not"""
    user = users_collection.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "balance": INITIAL_BALANCE,
            "last_daily": None
        }
        users_collection.insert_one(user)
    return user

async def get_balance(user_id: int) -> int:
    """Get user's balance"""
    user = await ensure_user_exists(user_id)
    return user["balance"]

# Checking balance
@client.tree.command(name="bal", description=f"Check your {CURRENCY_NAME} balance", guild=GUILD_ID)
async def balance(interaction: discord.Interaction, user: discord.Member = None):

     # If no user is specified, check own balance
    target_user = user if user else interaction.user
    user_balance = await get_balance(target_user.id)

    if target_user == interaction.user:
        title="💰 Balance Check"
        description = f"You have ₾**{user_balance:,}** {CURRENCY_NAME} 🧚💨"
    else:
        title = f"💰 {target_user.display_name}'s Balance"
        description = f"They have ₾**{user_balance:,}** {CURRENCY_NAME} 🧚💨"
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xfa99e7
    )
    
    await interaction.response.send_message(embed=embed)

# Viewing leaderboard
@client.tree.command(name="leader", description=f"Shows the top 5 richest users", guild=GUILD_ID)
async def leaderboard(interaction: discord.Interaction):
    # Get top 5 users sorted by balance
    top_users = list(users_collection.find().sort("balance", -1).limit(5))
    
    embed = discord.Embed(
        title="🏆 Richest Users",
        description=f"Top 5 {CURRENCY_NAME}🧚💨 holders",
        color=0xfa99e7
    )
    
    # Medals for top 3
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    
    for i, user_data in enumerate(top_users):
        try:
            # Get discord user object
            user = await client.fetch_user(user_data["_id"])
            # Format balance with commas
            balance = f"{user_data['balance']:,}"
            # Add field for this user
            embed.add_field(
                name=f"{medals[i]} {user.display_name}",
                value=f"₾ {balance} {CURRENCY_NAME}",
                inline=False
            )
        except discord.NotFound:
            continue
    
    embed.set_thumbnail(url="https://tikolu.net/i/tcicn.png")
    embed.set_footer(text=f"Use /balance to check your {CURRENCY_NAME}")
    
    await interaction.response.send_message(embed=embed)

# Check if user can claim daily
async def can_claim_daily(user_id: int) -> bool:

    """Check if user can claim daily reward"""
    user = users_collection.find_one({"_id": user_id})
    if not user or "last_daily" not in user or user["last_daily"] is None:
        return True
    last_claim = user["last_daily"]
    next_claim = last_claim + timedelta(days=1)
    return datetime.now() >= next_claim

# Let user claim daily
@client.tree.command(name="daily", description=f"Claim your daily {CURRENCY_NAME}", guild=GUILD_ID)
async def daily(interaction: discord.Interaction):
    # Ensure user exists
    await ensure_user_exists(interaction.user.id)
    
    # Check if user can claim
    if not await can_claim_daily(interaction.user.id):
        user = users_collection.find_one({"_id": interaction.user.id})
        next_claim = user["last_daily"] + timedelta(days=1)
        time_left = next_claim - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        embed = discord.Embed(
            title="❌ Daily Reward",
            description=f"You've already claimed your daily reward!\nCome back in **{hours}h {minutes}m**",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Generate random reward
    reward = random.randint(1, 100)
    
    # Update user's balance and last claim time
    users_collection.update_one(
        {"_id": interaction.user.id},
        {
            "$inc": {"balance": reward},
            "$set": {"last_daily": datetime.now()}
        }
    )
    
    # Get new balance
    new_balance = await get_balance(interaction.user.id)
    
    # Create embed response
    embed = discord.Embed(
        title="✨ Daily Reward Claimed!",
        description=f"You received **₾{reward:,}** {CURRENCY_NAME}🧚💨!",
        color=0x059415
    )
    embed.add_field(
        name="New Balance",
        value=f"₾{new_balance:,} {CURRENCY_NAME}🧚💨",
        inline=False
    )

    embed.set_footer(text="Come back tomorrow for another reward!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Give another user some fairy dust
@client.tree.command(name="give", description=f"Give another user some {CURRENCY_NAME}", guild=GUILD_ID)
async def give(interaction: discord.Interaction, amount: int, user: discord.Member):
    # Check if amount is valid
    if amount < 1:
        await interaction.response.send_message("❌You must give at least 1 fairy dust!", ephemeral=True)
        return
    
    # Check if user is trying to give to themselves
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌You can't give fairy dust to yourself!", ephemeral=True)
        return

    # Ensure both users exist and get balances
    await ensure_user_exists(interaction.user.id)
    await ensure_user_exists(user.id)
    
    sender_balance = await get_balance(interaction.user.id)
    
    # Check if sender has enough balance
    if sender_balance < amount:
        await interaction.response.send_message("❌You don't have enough fairy dust to give!", ephemeral=True)
        return
    
    # Update balances
    users_collection.update_one(
        {"_id": interaction.user.id},
        {"$inc": {"balance": -amount}}
    )
    users_collection.update_one(
        {"_id": user.id},
        {"$inc": {"balance": amount}}
    )
    
    # Get new balances
    new_sender_balance = await get_balance(interaction.user.id)
    new_receiver_balance = await get_balance(user.id)
    
    # Create embed response
    embed = discord.Embed(
        title="🎁 Fairy Dust Gifted!",
        description=f"You successfully gave **₾{amount:,}** {CURRENCY_NAME}🧚💨 to {user.mention}!",
        color=0x059415
    )
    embed.add_field(
        name="Your New Balance",
        value=f"₾{new_sender_balance:,} {CURRENCY_NAME}🧚💨",
        inline=False
    )
    embed.add_field(
        name=f"{user.display_name}'s New Balance",
        value=f"₾{new_receiver_balance:,} {CURRENCY_NAME}🧚💨",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# Locking betting line, for use in reaction button or from scheduled locking
def locking(message):

    old_embed = message.embeds[0]

    # Create new embed with locked status
    new_embed = discord.Embed(
        title=f"🔒 {old_embed.title}",
        description=old_embed.description,
        color=0xfce11b  # Amber color to indicate locked/pending results
    )

    # Copy all fields
    for field in old_embed.fields:
        new_embed.add_field(
            name=field.name,
            value=field.value,
            inline=field.inline
        )
    
    # Copy other attributes
    if old_embed.thumbnail:
        new_embed.set_thumbnail(url=old_embed.thumbnail.url)
    if old_embed.author:
        new_embed.set_author(
            name=old_embed.author.name,
            icon_url=old_embed.author.icon_url
        )
    new_embed.set_footer(text="🔒 This betting line is now LOCKED and pending results")

    bets_collection.update_one({"message_id": message.id}, {"$set": {"locked": True}})

    return new_embed

# Locking button
class LockButton(View):
    def __init__(self):
        super().__init__(timeout=None)

        lock_button = Button(
            style=discord.ButtonStyle.primary,
            emoji="🔒",
            custom_id="lock_bet"
        )

        self.add_item(lock_button)

        # Locking a betting line
        async def lock_callback(interaction: discord.Interaction):
            # Check if admin
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only oddsmakers can lock betting lines!", ephemeral=True)
                return
            
            message = interaction.message
            new_embed = locking(message)
            await message.edit(embed=new_embed, view=None)
            
            await interaction.response.send_message("✅ Betting line locked!", ephemeral=True)
    
        lock_button.callback = lock_callback

# For admin to create a betting line
@client.tree.command(name="cl", description="Creates a betting line, usage: /cl <title> <descrip> <ID> <outcomes|probabilities> <lock>", guild=GUILD_ID)    
async def create_line(interaction: discord.Interaction, title: str, description: str, outcomes: str, locks: str = None, restricted1: discord.Member = None, restricted2: discord.Member = None, restricted3: discord.Member = None):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    last_bet = bets_collection.find_one(sort=[("id", -1)])
    bet_id = last_bet["id"] + 1

    betting_data = odds(outcomes)
    embed = discord.Embed(title=f"{title} (Bet ID: #{str(bet_id)})", description=description, color=0x03c2fc)
    i = 1
    for outcome, info in betting_data.items():
        embed.add_field(name=f"Outcome {str(i)}: {outcome}", value=f"🎲Moneyline: {info['moneyline']}", inline=False)
        i += 1
    embed.set_thumbnail(url="https://tikolu.net/i/tcicn.png")
    embed.set_author(name="covid bets", icon_url="https://tikolu.net/i/miixg")
    if locks is not None:
        embed.set_footer(text=f"This line locks on {locktime(locks)}")
    else:
        embed.set_footer(text="❗This line has no set lock time, but it may be locked at any time")

    view = LockButton()
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    embed_id = message.id

    banned_IDS = []
    for crodie in [restricted1, restricted2, restricted3]:
        if crodie is not None:
            banned_IDS.append(crodie.id)

    bets_collection.insert_one(
        {
            "id": bet_id,
            "title": title,
            "outcomes": outcomes,
            "locks": datetime.strptime(locks, "%m/%d/%Y %H:%M") if locks is not None else None,
            "locked": False,
            "message_id": embed_id,
            "channel_id": interaction.channel.id,
            "restricted_users": banned_IDS,
            "participants": []
        }
    )

# Betting on a line
@client.tree.command(name="bet", description="Places bet, usage: /bet <amount> <outcome #> <bet ID>", guild=GUILD_ID)
async def place_bet(interaction: discord.Interaction, bet_id: int, outcome: int, amount: float):
    
    user = await ensure_user_exists(interaction.user.id)
    user_id = user["_id"]

    try:
        bet = bets_collection.find_one({"id": bet_id})
        if not bet:
            await interaction.response.send_message(f"❌ Bet with ID #{bet_id} not found!", ephemeral=True)
            return
    except Exception as e:
        await interaction.response.send_message(f"❌ Error finding bet: {str(e)}", ephemeral=True)
        return

    if user_id in bet["restricted_users"]:
        await interaction.response.send_message("❌ You are not allowed to bet on this line due to a conflict of interest!", ephemeral=True)
        return
    elif user_id in bet["participants"]:
        await interaction.response.send_message("❌ You have already a bet on this line!", ephemeral=True)
        return
    elif bet["locked"]:
        await interaction.response.send_message("❌ This betting line is no longer accepting bets!", ephemeral=True)
        return 
    elif user["balance"] < amount:
        await interaction.response.send_message(f"❌ You don't have enough {CURRENCY_NAME}🧚💨 to place this bet!", ephemeral=True)
        return
    elif outcome < 1 or outcome > len(bet["outcomes"].split(',')):
        await interaction.response.send_message("❌ Invalid outcome number!", ephemeral=True)
        return
    
    # Get betting data
    try:
        betting_data = odds(bet["outcomes"])
        outcome_name = list(betting_data.keys())[outcome - 1]
        payout = amount * betting_data[outcome_name]["decimal_odds"]
    except:
        await interaction.response.send_message("❌ Failed to place bet. Please check request input and try again!", ephemeral=True)
        return
   
    # Create confirmation embed
    embed = discord.Embed(
        title="🎲 Bet Confirmation",
        description=f"Please react with ✅ to confirm or ❌ to cancel your bet:",
        color=0x03c2fc
    )
    embed.add_field(
        name="Bet Details",
        value=f"Amount: ₾**{amount:,}** {CURRENCY_NAME}🧚💨\n"
              f"Outcome: **{outcome_name}**\n"
              f"Potential Payout: ₾**{payout:,.2f}** {CURRENCY_NAME}🧚💨\n"
              f"Bet ID: #{bet_id}",
        inline=False
    )

    # Send confirmation message
    await interaction.response.send_message(embed=embed, ephemeral=False)
    conf_message = await interaction.original_response()
    
    # Add reactions
    await conf_message.add_reaction("✅")
    await conf_message.add_reaction("❌")

    def check(reaction, reaction_user):
        return reaction_user.id == interaction.user.id and str(reaction.emoji) in ["✅", "❌"] and reaction.message == conf_message
    
    try:
        reaction, _ = await client.wait_for("reaction_add", timeout=15.0, check=check)

        if str(reaction.emoji) == "✅":
            # Get fresh user data to check balance again
            current_user = await ensure_user_exists(interaction.user.id)
            if current_user["balance"] < amount:
                error_embed = discord.Embed(
                    title="❌ Insufficient Balance",
                    description=f"You don't have enough {CURRENCY_NAME}🧚💨 to place this bet!",
                    color=0xff0000
                )
                await conf_message.edit(embed=error_embed)
                return

            # Update user balance
            users_collection.update_one({"_id": user_id}, {"$inc": {"balance": -amount}})
            
            # Add to user's open bets
            users_collection.update_one(
                {"_id": user_id}, 
                {"$push": {"bets": {
                    "bet_id": bet_id, 
                    "outcome_num": outcome,
                    "outcome": outcome_name, 
                    "amount": amount, 
                    "payout": payout, 
                    "result": None,
                    "placed_at": datetime.now()
                }}}
            )
            
            # Add user's ID to bet's participants
            bets_collection.update_one(
                {"id": bet_id}, 
                {"$push": {"participants": user_id}}
            )

            # Success embed
            success_embed = discord.Embed(
                title="✅ Bet Placed Successfully!",
                description=f"Your bet has been confirmed.",
                color=0x00ff00
            )
            success_embed.add_field(
                name="Bet Details",
                value=f"Amount: ₾**{amount:,}** {CURRENCY_NAME}🧚💨\n"
                      f"Outcome: **{outcome_name}**\n"
                      f"Potential Payout: ₾**{payout:,.2f}** {CURRENCY_NAME}🧚💨\n"
                      f"Bet ID: #{bet_id}",
                inline=False
            )
            await conf_message.edit(embed=success_embed)

        else:
            cancel_embed = discord.Embed(
                title="❌ Bet Cancelled",
                description="Your bet has been cancelled.",
                color=0xff0000
            )
            await conf_message.edit(embed=cancel_embed)

    except TimeoutError:
        timeout_embed = discord.Embed(
            title="⏰ Timeout",
            description="Bet confirmation timed out.",
            color=0xff0000
        )
        await conf_message.edit(embed=timeout_embed)

    try:
        await conf_message.clear_reactions()
    except:
        pass

# Update odds for a betting line
@client.tree.command(name="uo", description="Update odds for a betting line, usage: !uo <bet ID> <outcomes|probabilities>", guild=GUILD_ID)
async def update_odds(interaction: discord.Interaction, bet_id: int, outcomes: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    bet = bets_collection.find_one({"id": bet_id})
    if not bet:
        await interaction.response.send_message(f"Bet with ID {bet_id} not found!", ephemeral=True)
        return
    
    betting_data = odds(outcomes)
    message_id = bet["message_id"]
    channel_id = bet["channel_id"]
    channel = client.get_channel(channel_id)
    message = await channel.fetch_message(message_id)

    old_embed = message.embeds[0]
    new_embed = discord.Embed(
            title=old_embed.title,
            description=old_embed.description,
            color=old_embed.color
        )
    
    i = 1
    for outcome, info in betting_data.items():
        new_embed.add_field(name=f"Outcome {str(i)}: {outcome}", value=f"🎲Moneyline: {info['moneyline']}", inline=False)
        i += 1
    
    new_embed.set_thumbnail(url=old_embed.thumbnail.url)
    new_embed.set_author(name=old_embed.author.name, icon_url=old_embed.author.icon_url)
    new_embed.set_footer(text=old_embed.footer.text)

    await message.edit(embed=new_embed)
    bets_collection.update_one({"id": bet_id}, {"$set": {"outcomes": outcomes}})

    await interaction.response.send_message(f"Updated odds for bet ID {bet_id}", ephemeral=True)

# Close/anull a betting line
@client.tree.command(name="close", description="Close a betting line, usage: !close <bet ID> <reason>", guild=GUILD_ID)
async def close_bet(interaction: discord.Interaction, bet_id: int, reason: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    bet = bets_collection.find_one({"id": bet_id})
    if not bet:
        await interaction.response.send_message(f"Bet with ID {bet_id} not found!", ephemeral=True)
        return
    
    title = bet["title"]
    participants = bet["participants"]
    
    # Process refunds for each participant
    for user_id in participants:
        user_doc = users_collection.find_one({"_id": user_id})
        if user_doc and "bets" in user_doc:
            # Find the specific bet for this user
            for user_bet in user_doc["bets"]:
                if user_bet.get("bet_id") == bet_id:
                    # Refund the wagered amount
                    amount_wagered = user_bet.get("amount", 0)
                    users_collection.update_one(
                        {"_id": user_id},
                        {
                            "$inc": {"balance": amount_wagered},  # Refund the amount
                            "$pull": {"bets": {"bet_id": bet_id}}  # Remove the bet
                        }
                    )
    
    # Delete the bet
    bets_collection.delete_one({"id": bet_id})
    
    # Delete the original message
    try:
        message = await interaction.channel.fetch_message(bet["message_id"])
        await message.delete()
    except:
        pass  # Message might already be deleted

    # Create ping string for all participants
    toPing = " ".join(f"<@{user_id}>" for user_id in participants)

    embed = discord.Embed(
        title="Betting Line Closed",
        description=f"""Please be alerted that Bet ID #{bet_id} "**{title}**" has been annulled.\nAll wagered amounts have been refunded.""",
        color=0xff0000  # Red color for closure
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    if toPing:
        embed.add_field(name="Relevant Participants", value=toPing, inline=False)

    await interaction.response.send_message(embed=embed)

# Resolve a betting line
@client.tree.command(name="resolve", description="Resolve a betting line", guild=GUILD_ID)
async def resolve_bet(interaction: discord.Interaction, bet_id: int, winning_outcome: int, outcome: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
        return
    
    # Find the bet
    bet = bets_collection.find_one({"id": bet_id})
    if not bet:
        await interaction.response.send_message(f"Bet with ID {bet_id} not found!", ephemeral=True)
        return
    
    title = bet["title"]
    participants = bet["participants"]
    winners = []
    losers = []
    
    # Process payouts for each participant
    for user_id in participants:
        user_info = users_collection.find_one({"_id": user_id})
        if not user_info or "bets" not in user_info:
            continue
        
        # Find the relevant bet
        relevant_bet = next(
            (bet for bet in user_info["bets"] if bet["bet_id"] == bet_id),
            None
        )
        
        if relevant_bet:
            amount_wagered = relevant_bet["amount"]
            predicted = relevant_bet["outcome"]
            outcome_num = relevant_bet["outcome_num"]
            potential_payout = relevant_bet["payout"]
            
            if outcome_num == winning_outcome:
                # User won
                receipt = {
                    "bet": title,
                    "result": "win",
                    "prediction": predicted,
                    "wagered": amount_wagered,
                    "amount_won": potential_payout - amount_wagered,
                    "resolved_at": datetime.now()
                }
                users_collection.update_one(
                    {"_id": user_id},
                    {
                        "$inc": {"balance": potential_payout},
                        "$pull": {"bets": {"bet_id": bet_id}},
                        "$push": {"history": receipt}
                    }
                )
                winners.append({
                    "user_id": user_id,
                    "payout": potential_payout,
                    "wagered": amount_wagered
                })
            else:
                # User lost
                receipt = {
                    "bet": title,
                    "result": "loss",
                    "prediction": predicted,
                    "wagered": amount_wagered,
                    "resolved_at": datetime.now()
                }
                # Fixed update operation for losers
                users_collection.update_one(
                    {"_id": user_id},
                    {
                        "$pull": {"bets": {"bet_id": bet_id}},
                        "$push": {"history": receipt}
                    }
                )
                losers.append({
                    "user_id": user_id,
                    "wagered": amount_wagered
                })
    
    # Create result embed
    embed = discord.Embed(
        title="🎲 Betting Results",
        description=f"Results for **{title}**\nWinning Outcome: **{outcome}**",
        color=0x00ff00
    )
    
    # Add winners section
    if winners:
        winners_text = "\n".join(
            f"<@{w['user_id']}> - Won ₾**{w['payout']:,.2f}** (Bet: ₾{w['wagered']:,.2f})"
            for w in winners
        )
        embed.add_field(name="🏆 Winners", value=winners_text, inline=False)
    
    # Add losers section
    if losers:
        losers_text = "\n".join(
            f"<@{l['user_id']}> - Lost ₾**{l['wagered']:,.2f}**"
            for l in losers
        )
        embed.add_field(name="❌ Losers", value=losers_text, inline=False)
    
    # Delete the original bet message
    try:
        message = await interaction.channel.fetch_message(bet["message_id"])
        await message.delete()
    except:
        pass
    
    # Delete the bet from database
    bets_collection.delete_one({"id": bet_id})
    
    await interaction.response.send_message(embed=embed)

# See open bets
@client.tree.command(name="open", description="View your open bets", guild=GUILD_ID)
async def open_bets(interaction: discord.Interaction):
    user = await ensure_user_exists(interaction.user.id)
    if "bets" not in user or not user["bets"]:
        await interaction.response.send_message("You have no open bets!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎲 Open Bets",
        description="Here are your current open bets:",
        color=0x03c2fc
    )
    
    for placed in user["bets"]:
        bet = bets_collection.find_one({"id": placed["bet_id"]})
        embed.add_field(
            name=f"Bet ID #{bet['id']} - {bet['title']}",
            value=(f"Outcome: **{placed['outcome']}**\n"
                f"Wagered Amount: ₾**{placed['amount']:,.2f}** {CURRENCY_NAME}🧚💨\n"
                f"Payout: ₾**{placed['payout']:,.2f}** {CURRENCY_NAME}🧚💨\n"
                f"Placed: {locktime(placed['placed_at'])}"),
            inline=False
        )

    embed.set_thumbnail(url="https://tikolu.net/i/tcicn.png")
    
    await interaction.response.send_message(embed=embed)

# Start the bot
TOKEN = os.getenv('DISCORD_TOKEN')
client.run(TOKEN)
