FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем директории для входных и выходных файлов
RUN mkdir -p /app/input /app/output /app/logs

# Запускаем парсер
CMD ["python", "parser.py"]
