import os
import time
import csv
import json
import logging
from flask import Flask, render_template_string, request, jsonify
from google import genai
import requests

# إعداد السجلات لمتابعة عمل الخادم
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ==========================================
# الإعدادات الأساسية وتوكن تليجرام
# ==========================================
TELEGRAM_BOT_TOKEN = "9245115292:AAE2NI21HoATEQSrj7M9wxbM82s-gJyNca4"
CSV_FILE = "trainees_data.csv"
CHAT_LOG_FILE = "chat_history.json"

# تهيئة ملف الإكسل/CSV إذا لم يكن موجوداً
if not os.path.exists(CSV_FILE):
    try:
        with open(CSV_FILE, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Trainee Name", "Contact/Email", "Specialty", "Question", "Status"])
        log.info("تم إنشاء ملف trainees_data.csv بنجاح.")
    except Exception as e:
        log.error(f"خطأ في إنشاء ملف الإكسل: {e}")

# تهيئة ملف حفظ المحادثات إذا لم يكن موجوداً
if not os.path.exists(CHAT_LOG_FILE):
    try:
        with open(CHAT_LOG_FILE, mode="w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        log.info("تم إنشاء ملف chat_history.json لحفظ المحادثات بنجاح.")
    except Exception as e:
        log.error(f"خطأ في إنشاء ملف المحادثات: {e}")

# ==========================================
# إعدادات التخصصات والذاكرة الذاتية
# ==========================================
SPECIALTIES = {
    "chem": {
        "name": "تخصص الكيمياء",
        "memory_file": "chem_memory.txt",
        "trainer_telegram_id": "1140000516", 
        "prompt": "أنت خبير ومعلم خبير في الكيمياء لدعم المتدربين لرخصة التثقيف المهني. طبق السقالات التعليمية ولا تعطِ الحل النهائي مباشرة. إذا لم تكن متأكداً تماماً، اذكر بوضوح أنك ستحيل السؤال للمدرب."
    },
    "edu": {
        "name": "التربويات والتعليم",
        "memory_file": "edu_memory.txt",
        "trainer_telegram_id": "1140000516", 
        "prompt": "أنت خبير تربوي ومعلم خبير لدعم المتدربين في التربويات والتعليم. طبق السقالات التعليمية. إذا لم تكن متأكداً تماماً، اذكر بوضوح أنك ستحيل السؤال للمدرب."
    },
    "tahsili": {
        "name": "التحصيلي علمي",
        "memory_file": "tahsili_memory.txt",
        "trainer_telegram_id": "1140000516", 
        "prompt": "أنت خبير أكاديمي متخصص في اختبار التحصيلي علمي (أحياء، فيزياء، كيمياء، رياضيات). قدم شروحات مبسطة وقواعد واستراتيجيات لحل أسئلة التحصيلي. إذا لم تكن متأكداً تماماً، اذكر بوضوح أنك ستحيل السؤال للمدرب."
    }
}

for key, data in SPECIALTIES.items():
    if not os.path.exists(data["memory_file"]):
        with open(data["memory_file"], "w", encoding="utf-8") as f:
            f.write("سجل إجابات المدربين السابقة والتعلم الذاتي:\n")

def load_memory(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def save_chat_log(trainee_name, email, specialty, user_message, bot_response):
    try:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trainee_name": trainee_name,
            "email": email,
            "specialty": specialty,
            "user_message": user_message,
            "bot_response": bot_response
        }
        history = []
        if os.path.exists(CHAT_LOG_FILE):
            with open(CHAT_LOG_FILE, mode="r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = []
        history.append(log_entry)
        with open(CHAT_LOG_FILE, mode="w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        log.error(f"خطأ في حفظ سجل المحادثة: {e}")

def save_to_excel(t_name, t_contact, spec_name, question, status):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(CSV_FILE, mode="a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, t_name, t_contact, spec_name, question, status])
        log.info("تم تسجيل البيانات في ملف الإكسل بنجاح.")
    except Exception as e:
        log.error(f"خطأ في حفظ البيانات في الإكسل: {e}")

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        log.error(f"فشل إرسال تليجرام: {e}")

# ==========================================
# واجهة الويب (HTML / CSS)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>رفيق المتدرب (يتعلم ذاتياً)</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Cairo', sans-serif; }</style>
</head>
<body class="bg-slate-900 text-slate-100 h-screen flex flex-col justify-between">
    <header class="bg-slate-800 border-b border-slate-700 p-4 flex justify-between items-center shadow-md">
        <h1 class="text-lg font-bold text-yellow-400">🟡 رفيق المتدرب (يتعلم ذاتياً)</h1>
        <div class="flex gap-2">
            <input type="text" id="traineeName" placeholder="اسمك الكريم" class="bg-slate-700 px-3 py-1 rounded text-sm outline-none border border-slate-600 focus:border-yellow-400">
            <input type="email" id="traineeEmail" placeholder="إيميلك الشخصي" class="bg-slate-700 px-3 py-1 rounded text-sm outline-none border border-slate-600 focus:border-yellow-400">
            <select id="specSelect" class="bg-slate-700 px-3 py-1 rounded text-sm outline-none border border-slate-600 text-yellow-300 font-semibold">
                <option value="chem">🧪 تخصص الكيمياء</option>
                <option value="edu">📚 تخصص التربويات</option>
                <option value="tahsili">🎯 التحصيلي علمي</option>
            </select>
        </div>
    </header>

    <main id="chatBox" class="flex-1 overflow-y-auto p-4 space-y-4 max-w-4xl w-full mx-auto">
        <div class="bg-slate-800 p-4 rounded-xl shadow border border-slate-700 max-w-xl">
            أهلاً بك يا غالي 🌟 أنا رفيقك الذكي. كلما علّمتني شيئاً جديداً أصبحت أذكى وأسرع في خدمتك! اكتب اسمك وإيميلك واطرح سؤالك لنبدأ.
        </div>
    </main>

    <footer class="bg-slate-800 p-4 border-t border-slate-700">
        <div class="max-w-4xl mx-auto flex gap-2">
            <textarea id="userInput" rows="1" placeholder="اطرح سؤالك هنا..." class="flex-1 bg-slate-700 p-3 rounded-lg outline-none border border-slate-600 focus:border-yellow-400 resize-none"></textarea>
            <button onclick="sendMessage()" class="bg-yellow-500 hover:bg-yellow-600 text-slate-950 font-bold px-6 py-2 rounded-lg transition">إرسال</button>
        </div>
    </footer>

    <script>
        async function sendMessage() {
            const name = document.getElementById("traineeName").value.trim();
            const email = document.getElementById("traineeEmail").value.trim();
            const spec = document.getElementById("specSelect").value;
            const input = document.getElementById("userInput");
            const text = input.value.trim();
            const chatBox = document.getElementById("chatBox");

            if(!name || !email) {
                alert("الرجاء كتابة الاسم والإيميل أولاً!");
                return;
            }
            if(!text) return;

            chatBox.innerHTML += `<div class="bg-indigo-600 p-3 rounded-xl max-w-xl mr-auto">${text}</div>`;
            input.value = "";
            chatBox.scrollTop = chatBox.scrollHeight;

            try {
                const res = await fetch("/ask", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ name, email, spec, message: text })
                });
                const data = await res.json();
                chatBox.innerHTML += `<div class="bg-slate-800 p-3 rounded-xl max-w-xl border border-slate-700">${data.reply}</div>`;
                chatBox.scrollTop = chatBox.scrollHeight;
            } catch(e) {
                chatBox.innerHTML += `<div class="bg-red-600 p-3 rounded-xl max-w-xl">حدث خطأ في الاتصال بالخادم.</div>`;
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    name = data.get("name", "مجهول")
    email = data.get("email", "")
    spec_key = data.get("spec", "chem")
    user_msg = data.get("message", "")

    spec = SPECIALTIES.get(spec_key, SPECIALTIES["chem"])
    memory_content = load_memory(spec["memory_file"])

    client = genai.Client()
    full_prompt = f"""
    {spec['prompt']}
    ذاكرة المحتوى المكتسبة السابقة والأسئلة المحالة:
    {memory_content}
    سؤال المتدرب الحالي: {user_msg}
    إذا كانت إجابة السؤال غير مؤكدة تماماً في الذاكرة أو تتطلب تدخلاً بشرياً، ابدأ ردك بكلمة "إحالة:" واشرح للمتدرب أنه تم تحويل سؤاله للمدرب. وإلا فقدم الإجابة.
    """

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=full_prompt)
        reply = response.text
    except Exception as e:
        reply = f"عذراً، حدث خطأ أثناء الاتصال بنموذج الذكاء الاصطناعي: {e}"

    if "إحالة:" in reply or "سيتم التواصل معك" in reply:
        save_to_excel(name, email, spec["name"], user_msg, "معلق لإجابة المدرب")
        trainer_id = spec.get("trainer_telegram_id", "").strip()
        if trainer_id:
            alert_text = f"🚨 **تنبيه إحالة سؤال جديد عبر الويب**\n\n📌 **التخصص:** {spec['name']}\n👤 **الاسم:** {name}\n📧 **الإيميل:** {email}\n❓ **السؤال:** {user_msg}"
            send_telegram_message(trainer_id, alert_text)
    else:
        save_to_excel(name, email, spec["name"], user_msg, "تم الرد تلقائياً")

    save_chat_log(name, email, spec["name"], user_msg, reply)
    return jsonify({"reply": reply})

# ==========================================
# مسار استقبال رسائل تليجرام التفاعلية (Webhook)
# ==========================================
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_text = msg.get("text", "")
        user_name = msg["from"].get("first_name", "متدرب تليجرام")
        
        spec = SPECIALTIES["chem"]
        memory_content = load_memory(spec["memory_file"])

        client = genai.Client()
        full_prompt = f"""
        {spec['prompt']}
        ذاكرة المحتوى المكتسبة السابقة:
        {memory_content}
        سؤال المتدرب عبر تليجرام: {user_text}
        إذا كانت الإجابة غير مؤكدة ابدأ بـ "إحالة:" وإلا أجب مباشرة.
        """

        try:
            response = client.models.generate_content(model="gemini-2.5-flash", contents=full_prompt)
            reply = response.text
        except Exception as e:
            reply = f"عذراً حدث خطأ: {e}"

        if "إحالة:" in reply:
            save_to_excel(user_name, f"Telegram ID: {chat_id}", spec["name"], user_text, "معلق من تليجرام")
            trainer_id = spec.get("trainer_telegram_id", "").strip()
            if trainer_id:
                send_telegram_message(trainer_id, f"🚨 **سؤال تليجرام معلق:**\nمن: {user_name}\nالسؤال: {user_text}")
        else:
            save_to_excel(user_name, f"Telegram ID: {chat_id}", spec["name"], user_text, "تم الرد عبر تليجرام")

        save_chat_log(user_name, f"Telegram ID: {chat_id}", spec["name"], user_text, reply)
        send_telegram_message(chat_id, reply)

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)