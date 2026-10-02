# NewAl Cloud (تجربة)

تطبيق أندرويد صغير ومستقل: محادثة برمجية تعتمد على APIs سحابية مجانية بدل نموذج GGUF محلي.

- واجهة OpenAI-compatible (`/chat/completions`) مع بث الرد (SSE) وزر إيقاف.
- مزودون جاهزون: Groq, Google AI Studio (Gemini), Cerebras, OpenRouter, Mistral + مزود مخصص.
- المفتاح والنموذج والرابط تُحفظ محلياً على الجهاز لكل مزود (SharedPreferences خاص بالتطبيق).
- أسماء النماذج الافتراضية قد تتقادم؛ عدّلها من ⚙.

## البناء
GitHub Actions ← Build APK ← Run workflow، ثم نزّل `NewAl-Cloud-debug` من Artifacts.

## ملاحظات
- لا يوجد llama.cpp ولا C++ هنا. التطبيق تجريبي ولا يشغّل Termux.
- الكود المرسل يذهب لطرف ثالث؛ راجع سياسة بيانات كل مزود (بعض المجانيات تُستخدم للتدريب).
