import telebot
import requests
import logging
import random
import csv
from apscheduler.schedulers.background import BackgroundScheduler
from telebot import types

TOKEN = "8134292143:AAHXhREWyjJFwryTDP5FGNRy21snvo0OO0E"
API_KEY = "82958e4c34effa73ab76ecd5810a66d1"
PARTNER_ID = "606741"
AIRPORTS_CSV = r"C:\\Users\\Влад и Юля\\Desktop\\Новая папка\\Lovi_belet\\airports_list.csv"

bot = telebot.TeleBot(TOKEN)
scheduler = BackgroundScheduler()

user_subscriptions = {}
user_flights_history = {}
user_cities = {}
user_destinations = {}

iata_to_city = {}
city_to_iata = {}

def load_airports():
    try:
        with open(AIRPORTS_CSV, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            for row in reader:
                if len(row) < 2:
                    continue
                iata, city = row[0].strip(), row[1].strip()
                iata_to_city[iata] = city
                city_to_iata[city.lower()] = iata
        print(f"✅ Загружено {len(iata_to_city)} аэропортов из CSV.")
    except Exception as e:
        logging.error(f"Ошибка загрузки CSV: {e}")

load_airports()

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("✈ Найти билеты")
    btn2 = types.KeyboardButton("📩 Подписаться на рассылку")
    btn3 = types.KeyboardButton("🌍 Изменить город вылета")
    btn4 = types.KeyboardButton("🏙 Выбрать город прилёта")
    btn5 = types.KeyboardButton("ℹ О боте")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

def get_cheapest_flights(origin, destination=None):
    url = "https://api.travelpayouts.com/v2/prices/latest"
    headers = {"X-Access-Token": API_KEY}
    params = {
        "currency": "rub",
        "origin": origin,
        "limit": 30,
        "show_to_affiliates": "true",
        "partner": PARTNER_ID,
        "one_way": True,
        "sorting": "price",
        "max_stopovers": 0
    }
    if destination:
        params["destination"] = destination

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return sorted(data.get("data", []), key=lambda x: x['value'])
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка API: {e}")
        return []

def generate_booking_link(origin, destination, depart_date):
    depart_date_parts = depart_date.split('-')
    if len(depart_date_parts) == 3:
        formatted_date = f"{depart_date_parts[2]}{depart_date_parts[1]}"
        return f"https://www.aviasales.ru/search/{origin}{formatted_date}{destination}1"
    return "https://www.aviasales.ru/"

def send_flight_offer(user_id):
    origin = user_cities.get(user_id, "MOW")
    destination = user_destinations.get(user_id)
    flights = get_cheapest_flights(origin, destination)
    if not flights:
        bot.send_message(user_id, "❌ Сейчас нет доступных предложений.")
        return

    user_history = user_flights_history.get(user_id, [])
    random.shuffle(flights)
    new_flights = []
    for flight in flights:
        flight_id = (flight['destination'], flight['depart_date'], flight['value'])
        if flight_id not in user_history:
            new_flights.append(flight)
            user_history.append(flight_id)
        if len(new_flights) >= 3:
            break

    if new_flights:
        message_text = "🔥 Самые выгодные билеты:\n\n"
        for flight in new_flights:
            price = flight.get('value', 'N/A')
            origin_code = flight.get('origin', 'N/A')
            destination = flight.get('destination', 'N/A')
            depart_date = flight.get('depart_date', 'N/A')
            origin_city = iata_to_city.get(origin_code, origin_code)
            destination_city = iata_to_city.get(destination, destination)
            booking_link = generate_booking_link(origin_code, destination, depart_date)

            message_text += (f"✈ {origin_city} → {destination_city}\n"
                             f"💰 {price} руб.\n"
                             f"📅 {depart_date}\n"
                             f"🔗 [Забронировать билет]({booking_link})\n\n")

        user_flights_history[user_id] = user_history
        bot.send_message(user_id, message_text, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        bot.send_message(user_id, "❌ Все предложения уже были отправлены.")

def send_daily_offers():
    for user_id in user_subscriptions.keys():
        send_flight_offer(user_id)

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "👋 Привет! Добро пожаловать в ЛовиБилет! ✈️\n\n"
                                      "🚀 Начнём? Используй меню ниже для навигации.",
                     reply_markup=main_menu())

@bot.message_handler(func=lambda message: True)
def handle_menu(message):
    if message.text == "✈ Найти билеты":
        search_flight(message)
    elif message.text == "📩 Подписаться на рассылку":
        subscribe(message)
    elif message.text == "🌍 Изменить город вылета":
        change_city(message)
    elif message.text == "🏙 Выбрать город прилёта":
        change_destination(message)
    elif message.text == "ℹ О боте":
        bot.send_message(message.chat.id, "🤖 Я — ЛовиБилет! Нахожу для тебя лучшие предложения на авиабилеты из Москвы. ✈️")
    else:
        bot.send_message(message.chat.id, "❌ Неизвестная команда. Используйте меню.", reply_markup=main_menu())

@bot.message_handler(commands=['subscribe'])
def subscribe(message):
    user_subscriptions[message.chat.id] = True
    bot.send_message(message.chat.id, "✅ Вы подписались на рассылку дешёвых авиабилетов!")

@bot.message_handler(commands=['search'])
def search_flight(message):
    user_id = message.chat.id
    if user_id not in user_cities:
        bot.send_message(user_id, "🛫 Введите город вылета:")
        bot.register_next_step_handler(message, set_user_city)
    elif user_id not in user_destinations:
        bot.send_message(user_id, "🏙 Введите город прилёта:")
        bot.register_next_step_handler(message, set_user_destination)
    else:
        send_flight_offer(user_id)

@bot.message_handler(commands=['change_city'])
def change_city(message):
    bot.send_message(message.chat.id, "🔄 Введите новый город вылета:")
    bot.register_next_step_handler(message, set_user_city)

@bot.message_handler(commands=['change_destination'])
def change_destination(message):
    bot.send_message(message.chat.id, "🏙 Введите новый город прилёта:")
    bot.register_next_step_handler(message, set_user_destination)

def set_user_city(message):
    user_id = message.chat.id
    city_name = message.text.strip().lower()
    iata_code = city_to_iata.get(city_name)
    if iata_code:
        user_cities[user_id] = iata_code
        bot.send_message(user_id, f"✅ Город вылета установлен: {city_name.capitalize()}", reply_markup=main_menu())
        if user_id in user_destinations:
            send_flight_offer(user_id)
    else:
        bot.send_message(user_id, "❌ Город не найден. Попробуйте ещё раз или используйте Москву по умолчанию.")

def set_user_destination(message):
    user_id = message.chat.id
    city_name = message.text.strip().lower()
    iata_code = city_to_iata.get(city_name)
    if iata_code:
        user_destinations[user_id] = iata_code
        bot.send_message(user_id, f"✅ Город прилёта установлен: {city_name.capitalize()}", reply_markup=main_menu())
        send_flight_offer(user_id)
    else:
        bot.send_message(user_id, "❌ Город не найден. Попробуйте ещё раз или используйте другой город.")

scheduler.add_job(send_daily_offers, 'interval', hours=6)
scheduler.start()

bot.polling(none_stop=True)
