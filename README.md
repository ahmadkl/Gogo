# استوديو الذكاء الاصطناعي

دردشة، توليد صور، فيديو من نص، تحريك صور، تمديد الفيديو، وشخصيات ثابتة المظهر.

## الهيكل
- `index.html`: الواجهة (يمكن نشرها على GitHub Pages).
- `server/`: خادم FastAPI يولّد مقاطع قصيرة، يربطها بـ ffmpeg، ويمدّد الفيديو من آخر إطار.

## ما يعمل مجاناً وما لا يعمل
- **الدردشة والصور:** تعمل مباشرة من المتصفح عبر Pollinations.ai بدون مفتاح.
- **الفيديو:** لا يوجد نموذج مجاني يولّد 10 دقائق دفعة واحدة. الخادم يولّد مقاطع 5 إلى 10 ثوان ثم يدمجها (10 دقائق = 60 إلى 120 مقطعاً). على Hugging Face Space المجاني سيكون ذلك بطيئاً جداً وقد يتوقف بسبب الحصص. الأفضل GPU خاص بك أو Google Colab.
- **الحفاظ على الشخصية:** يُطبّق بوصف ثابت + seed ثابت، وكل مقطع جديد يبدأ من آخر إطار للمقطع السابق. هذا يحسّن الثبات ولا يضمنه بالكامل. للدقة العالية درّب LoRA للشخصية.

## تشغيل الخادم
```bash
cd server
pip install -r requirements.txt   # ويلزم تثبيت ffmpeg
cp .env.example .env              # عدّل الإعدادات
export $(grep -v '^#' .env | xargs)
uvicorn main:app --port 8000
```
افتح http://localhost:8000 (الخادم يقدّم الواجهة أيضاً). الوضع الافتراضي `VIDEO_PROVIDER=mock` يولّد مقاطع اختبار ليتأكد أن الدمج والتمديد يعملان.

## ربط نموذج فيديو حقيقي
1. اختر Space مناسباً على Hugging Face (LTX-Video أو Wan أو CogVideoX لـ image-to-video).
2. افتح "Use via API" في صفحته وانسخ اسم الـ endpoint وأسماء المعاملات.
3. ضع في `.env`: `VIDEO_PROVIDER=gradio` و`HF_SPACE` و`HF_API_NAME` و`HF_PARAM_MAP` و`HF_EXTRA_PARAMS`.

## نشر الواجهة على GitHub Pages
Settings ثم Pages ثم Deploy from branch `main` / root. بعدها في تبويب "إعدادات" ضع عنوان خادمك. لا يعمل `http://localhost` من صفحة https على بعض المتصفحات، فاستخدم نفق (مثل Cloudflare Tunnel) أو شغّل الواجهة من الخادم نفسه.
