#!/bin/sh
# firewall_check.sh — БЛОКИРУЕТ push, если приватные данные попали в трекаемые git-файлы.
# Ритуал private/public-файрвола (по образцу moat-check): запускать перед каждым push
# к публикации. Имена приватных советников НЕ хардкодятся — выводятся из локального
# (gitignored) advisors/, чтобы сам скрипт не носил реальных имён живых людей в public.
# Скрипт исключает себя из скана, иначе его собственные паттерны дадут ложный FAIL.
#
# Подключить как git-хук (по желанию):  ln -s ../../scripts/firewall_check.sh .git/hooks/pre-push
set -e
self='scripts/firewall_check.sh'
fail=0

# PD-фигуры (public-domain корпуса) — их имена ЛЕГИТИМНО стоят в трекаемых доках/тестах/фикстурах.
# Всё остальное в advisors/ считается ПРИВАТНЫМ (живые люди из чужих корпусов) — fail-closed:
# новый советник запрещён к появлению в git, пока его имя явно не внесено в PD-allowlist.
PD_ALLOW='machiavelli|marcus-aurelius|sun-tzu|epictetus|seneca|aristotle'
# Список приватных имён = каталоги в advisors/ минус README минус PD-allowlist.
PRIV=$(ls advisors 2>/dev/null | grep -v '^README.md$' | grep -ivE "^($PD_ALLOW)$" | paste -sd'|' -)

# 1. приватные имена в именах ИЛИ теле трекаемых файлов (если локально есть советники)
if [ -n "$PRIV" ]; then
  if git ls-files | grep -iE "$PRIV"; then echo "FAIL: приватное имя в имени трекаемого файла"; fail=1; fi
  if git grep -liE "$PRIV" -- . ":!$self"; then echo "FAIL: приватное имя в теле трекаемого файла"; fail=1; fi
fi

# 2. секреты — паттерн ловит РЕАЛЬНЫЙ ключ (префикс+хвост), не голый префикс из доков
if git grep -lE 'sk-or-v1-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}' -- . ":!$self"; then
  echo "FAIL: похоже на секрет"; fail=1
fi

# 3. файлы, которые НИКОГДА не должны трекаться
for f in .env gov_heads.local.json principis.md relationship.md board_config.json; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then echo "FAIL: $f трекается"; fail=1; fi
done
if git ls-files | grep -E '^advisors/' | grep -qv '^advisors/README.md'; then
  echo "FAIL: advisors/* трекается (кроме README)"; fail=1
fi
if git ls-files | grep -Eq 'reference-library-raw/|-raw/'; then echo "FAIL: сырьё-raw трекается"; fail=1; fi

# 4. gov_heads.json содержит только шипуемые ключи (lenses/*), не advisors/*
if git show HEAD:gov_heads.json 2>/dev/null | grep -q '"advisors/'; then
  echo "FAIL: приватный якорь в трекаемом реестре gov_heads.json"; fail=1
fi

[ "$fail" = 0 ] && echo "firewall-check: OK" || { echo "firewall-check: ПРОВАЛ — push заблокирован"; exit 1; }
