# VHS-раскадровка демо «докажет или промолчит» (<10 сек, тёмная тема, ноль шума).
# Рендер:  vhs scripts/demo/refusal.tape   → assets/demo-refusal.gif
# Скрытый блок задаёт env офлайн-контура + функцию consilium, чтобы В КАДРЕ была
# чистая команда `consilium verify «Марк Аврелий»` без путей/JSON/env (Rule 1/10).
# Вердикты 🔵/🟡 считает живой гейт верности при запуске — не хардкод (см. refusal_demo.py).

Output assets/demo-refusal.gif

Require python3

Set Shell "bash"
Set FontSize 22
Set Width 1120
Set Height 620
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0

Hide
Type "export OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/refusal_demo.py --no-prompt; }" Enter
Type "clear" Enter
Show

Sleep 600ms
Type "consilium verify «Марк Аврелий»"
Sleep 500ms
Enter
Sleep 10s
