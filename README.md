# 🧪 Stalcraft Crafting Calculator

Калькулятор прибыли крафта для STALCRAFT: считает себестоимость по аукциону,
выбирает «купить или скрафтить», учитывает комиссию и энергию.

## Быстрый старт

```bash
pip install requests python-dotenv tzdata
cp .env.example .env
# заполните STALCRAFT_CLIENT_SECRET в .env
python main.py