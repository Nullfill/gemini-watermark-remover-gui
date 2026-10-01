# Watermark Remover — Universal Desktop Studio (Windows)

<p align="center">
  <img src="ui/preview_widget.py" alt="Watermark Remover" width="0" height="0">
  <b>نرم‌افزار حرفه‌ای، مستقل و مدرن ویندوز برای حذف انواع واترمارک، لوگو، آیدی، زیرنویس چسبیده و متن‌های ثابت از روی ویدیوها</b>
  <br>
  با بهره‌گیری از هوش مصنوعی <b>ProPainter (AI Inpainting)</b>، فیلتر سریع <b>Delogo</b> و <b>Crop</b>، حفظ کامل ساختار VFR/PTS و رنگ، بدون نیاز به نصب پایتون و بدون افت کیفیت.
</p>

<p align="center">
  <a href="https://github.com/Nullfill/gemini-watermark-remover-gui/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/Release-v1.0.0%20Portable-blue?style=for-the-badge&logo=windows" alt="Download Windows Release">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT">
  </a>
</p>

---

## 🌟 چه مواردی را می‌توان با این نرم‌افزار حذف کرد؟
این برنامه به یک سرویس یا لوگوی خاص محدود نیست و یک **سامانه جامع و همه‌منظوره** برای پاکسازی هرگونه المان ناخواسته از ویدیو است:
- **واترمارک ابزارهای تولید محتوا و هوش مصنوعی**: ویدیوهای خروجی Google Gemini / Veo، Sora، Runway Gen-2، Pika، CapCut، InShot، KineMaster، Filmora و ...
- **لوگو و آرم شبکه‌ها و پلتفرم‌ها**: لوگوی شبکه‌های تلویزیونی، آرم پلتفرم‌های پخش فیلم (آپارات، فیلیمو، نماوا، یوتیوب و...).
- **آیدی و نام کاربری شبکه‌های اجتماعی**: آیدی پیج‌های اینستاگرام، تیک‌تاک، چنل‌های تلگرام و توییتر.
- **تایمر و تاریخ دوربین‌ها**: متادیتاهای تاریخ، ساعت و مشخصات دوربین‌های مداربسته (CCTV)، داش‌کم و تجهیزات تصویربرداری.
- **زیرنویس‌های چسبیده (Hardsubs)**: حذف متون و زیرنویس‌های چاپی که داخل تصویر رندر شده‌اند.
- **هر آبجکت ثابت یا کادر دلخواه**: کافی است کادر قرمز را با ماوس روی هر شیء ناخواسته‌ای بکشید تا با هوش مصنوعی بازسازی و محو شود.

---

## 🎯 ۴ روش آسان برای مشخص کردن محدوده واترمارک
1. **جابجایی تعاملی و دستی با ماوس (Interactive Visual Drag & Resize)**: روی کادر قرمز در پیش‌نمایش تصویر کلیک کنید و آن را به هر نقطه‌ای از کادر بکشید. با کشیدن دستگیره‌های گوشه، اندازه آن را دقیقاً بر روی ابعاد لوگو یا متن فیت کنید.
2. **تشخیص خودکار هوشمند (Auto-Detect Watermark)**: الگوریتم تحلیل زمانی، لبه‌های پایدار و ثابت در طول زمان را جستجو کرده و کادر را به شکل خودکار بر روی لوگو تنظیم می‌کند.
3. **پیش‌تنظیم ۴ گوشه (Corner Presets)**: با یک کلیک روی دکمه‌های `Top Left`، `Top Right`، `Bottom Left` یا `Bottom Right` کادر فوراً به گوشه متناظر هدایت می‌شود.
4. **تنظیم دقیق پیکسلی (SpinBoxes)**: برای بالاترین دقت، مقادیر عددی `X`، `Y`، `Width` و `Height` به صورت پیکسل به پیکسل قابل ویرایش هستند.

---

## 🚀 ویژگی‌های کلیدی برنامه
- **سه متد قدرتمند برای حذف**:
  1. **AI Inpaint (ProPainter)**: بازسازی بافت زیرین بر مبنای حرکت فریم‌های مجاور و شبکه عصبی انتشار نوری؛ بالاترین کیفیت بدون تار کردن تصویر (پیش‌فرض).
  2. **Delogo**: درون‌یابی پیکسل‌های حاشیه با موتور بومی FFmpeg؛ فوق‌العاده سریع (زیر ۲ ثانیه) و عالی برای پس‌زمینه‌های یکدست.
  3. **Crop**: بریدن هوشمند حاشیه یا نوار حاوی واترمارک و بازگرداندن مقیاس تصویر.
- **رابط کاربری مدرن (PySide6)**: پشتیبانی کامل از کشیدن و رها کردن فایل (Drag & Drop)، تم تیره حرفه‌ای، و معماری چند نخی بدون فریز شدن UI.
- **مدیریت واقعی نرخ فریم متغیر (True VFR PTS Preservation)**: استخراج و بازسازی دقیق تایم‌استمپ‌های PTS فریم‌به‌فریم از ویدیوی ورودی با PyAV؛ جلوگیری قطعی از ناهماهنگی صدا و تصویر (Audio-Video Sync Drift).
- **حفظ تمامی استریم‌ها**: نگهداری تمام ترک‌های صوتی اورجینال، زیرنویس‌ها، چپترها و متادیتاها با نگاشت صریح استریم‌ها (`-map`).
- **تشخیص HDR و رنگ**: بررسی و حفظ متادیتای رنگ (`color_primaries`, `color_trc`, `colorspace`) و هشدار در صورت بارگذاری ویدیوی ۱۰ بیتی HDR.
- **نوار پیشرفت زنده (Real Progress Bar)**: نمایش درصد پیشرفت و شماره فریم لحظه‌ای (`Optical flow frame 120/1500 ...`) به همراه قابلیت لغو آنی (Instant Cancel) و پاکسازی دایرکتوری موقت.
- **امنیت فایل اصلی**: فایل ورودی کاربر هرگز بازنویسی نخواهد شد؛ خروجی‌ها با نام‌های ایمن نظیر `video_clean.mp4` ذخیره می‌شوند.

---

## 📦 دانلود و اجرای نسخه پرتابل ویندوز (بدون نیاز به نصب)

برای استفاده از برنامه، نیازی به نصب پایتون، گیت، FFmpeg یا هیچ پیش‌نیازی ندارید:
1. بسته پرتابل را از بخش [Releases](https://github.com/Nullfill/gemini-watermark-remover-gui/releases/tag/v1.0.0) یا لینک مستقیم زیر دانلود کنید:
   - [دانلود مستقیم WatermarkRemover-v1.0.0-windows-x64.zip](https://github.com/Nullfill/gemini-watermark-remover-gui/releases/download/v1.0.0/WatermarkRemover-v1.0.0-windows-x64.zip)
2. فایل فشرده را استخراج (Extract) کنید.
3. بر روی **`WatermarkRemover.exe`** دو بار کلیک کنید تا برنامه اجرا شود.

---

## 🛠️ ساختار ماژولار پروژه

```text
WatermarkRemover/
├── app.py                      # نقطه ورود اصلی نرم‌افزار گرافیکی (PySide6 GUI Entry Point)
├── dewatermark.py              # واسط خط فرمانی (CLI & Backward Compatibility)
├── WatermarkRemover.spec       # فایل پیکربندی PyInstaller جهت تولید باینری مستقل ویندوز
├── build.bat / build.ps1       # اسکریپت‌های اتوماسیون بیلد یکپارچه برای ویندوز
├── package_and_upload.py       # اسکریپت اتوماتیک پکیجینگ و آپلود در گیت‌هاب ریلیز
├── requirements.txt            # نیازمندی‌های زمان اجرای سورس پایتون
├── requirements-dev.txt        # پکیج‌های توسعه، کامپایل و پکیجینگ
├── ffmpeg/                     # باینری‌های مستقل محلی FFmpeg و FFprobe (بدون وابستگی به PATH)
├── models/                     # وزن‌های شبکه‌های عصبی ProPainter و RAFT
├── output/                     # دایرکتوری پیش‌فرض ذخیره‌سازی ویدیوهای پاکسازی‌شده
├── core/
│   ├── config.py               # مدیریت مسیرها، پایگاه QSettings و پاکسازی temp
│   ├── logger.py               # ثبت لاگ‌های چرخشی در logs/app.log و کنسول
│   ├── ffmpeg_runner.py        # نظارت بر پروسه‌های FFmpeg با پارسر پیشرفت pipe:1 و لغو آنی
│   ├── video_info.py           # آنالیز مشخصات کانتینر، تشخیص VFR/HDR و فریم پیش‌نمایش
│   ├── detection.py            # تحلیل پایداری زمانی لبه‌ها و محاسبه بهینه ابعاد پنجره کراپ
│   ├── models_manager.py       # اعتبارسنجی یکپارچگی فایل‌های مدل و دیالوگ دانلود خودکار
│   └── processor.py            # پردازشگر اصلی در پس‌زمینه (QThread)
├── propainter/                 # ماژول مستقل و یکپارچه‌شده ProPainter (کاملاً بومی)
├── ui/
│   ├── theme.py                # تم تیره مدرن و شکیل QSS
│   ├── preview_widget.py       # ویجت تعاملی پیش‌نمایش با کادر جابجاشونده و قابل ریسایز
│   ├── settings_dialog.py      # پنجره تنظیمات کیفیت (CRF)، دایرکتوری خروجی و شتاب سخت‌افزاری
│   ├── models_dialog.py        # پنجره مدیریت و دانلود وزن‌های مدل‌های هوش مصنوعی
│   └── main_window.py          # پنجره اصلی برنامه، Drag & Drop و مدیریت رویدادها
└── tests/
    └── test_all.py             # مجموعه تست‌های جامع برای ۱۶ سناریوی مختلف
```

---

## 💻 راه‌اندازی محیط توسعه (برای توسعه‌دهندگان)

### ۱. نصب وابستگی‌ها
```bash
python -m pip install -r requirements.txt
```

### ۲. اجرای رابط کاربری
```bash
python app.py
```

### ۳. اجرای خط فرمانی (CLI)
```bash
# تشخیص خودکار و حذف واترمارک با متد هوش مصنوعی
python dewatermark.py video.mp4

# حذف سریع در کمتر از ۲ ثانیه با روش Delogo
python dewatermark.py video.mp4 --method delogo --crf 18

# انتخاب دستی موقعیت گوشه (پایین-راست: br، پایین-چپ: bl، بالا-راست: tr، بالا-چپ: tl)
python dewatermark.py video.mp4 --corner br
```

### ۴. ساخت مجدد فایل اجرایی ویندوز
```powershell
.\build.ps1
```

---

## ⚡ فعال‌سازی شتاب‌دهی سخت‌افزاری NVIDIA CUDA
نرم‌افزار به صورت خودکار در منوی **Settings** امکان انتخاب میان `Auto`، `NVIDIA GPU (CUDA)` و `CPU` را به شما می‌دهد:
- برای استفاده از توان کارت گرافیک در محیط پایتون، نسخه سازگار با CUDA کتابخانه PyTorch را نصب نمایید:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```
- در حالت اجرای با GPU، سرعت پردازش هوش مصنوعی تا **۱۰ الی ۱۵ برابر** نسبت به CPU افزایش خواهد یافت.

---

## 📄 مجوزها و لایسنس
- این نرم‌افزار تحت مجوز [MIT License](LICENSE) منتشر شده است.
- ماژول هوش مصنوعی ProPainter متعلق به [S-Lab, NTU Singapore](https://github.com/sczhou/ProPainter) و تحت [S-Lab License 1.0](NOTICE_PROPAINTER.txt) است.
- فایل‌های باینری FFmpeg تحت [GNU GPL v3](NOTICE_FFMPEG.txt) توزیع شده‌اند.
