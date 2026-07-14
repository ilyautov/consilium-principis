# VHS storyboard, English demo "proves the quote or stays silent" (<10s, dark, zero noise).
# Render:  vhs scripts/demo/refusal.en.tape   → assets/demo-refusal-en.gif
# Hidden block sets the offline-contour env + a consilium function so the ON-SCREEN command
# stays clean (no paths/JSON/env, Rule 1/10). 🔵/🟡 verdicts come from the live fidelity gate
# at runtime, not hardcoded (see refusal_demo.py).

Output assets/demo-refusal-en.gif

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
Type "export HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/refusal_demo.py --no-prompt --en; }" Enter
Type "clear" Enter
Show

Sleep 600ms
Type "consilium verify Marcus Aurelius"
Sleep 500ms
Enter
Sleep 10s
