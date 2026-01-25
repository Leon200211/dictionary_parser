#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Парсер словарных статей из Word документов
Обрабатывает специальные теги и извлекает структурированные данные
"""

import os
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from docx import Document
from docx.text.paragraph import Paragraph


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DictionaryParser:
    """Парсер словарных статей"""

    # Регулярные выражения для тегов
    ARTICLE_START = '#'
    ARTICLE_END = '##'

    TAG_PATTERNS = {
        1: (r'\{1\}', r'\{1\}'),    # Заголовок
        2: (r'\{2\}', r'\{2\}'),    # Грамматические пометы
        3: (r'\{3\}', r'\{3\}'),    # Толкования
        4: (r'\{4\}', r'\{4\}'),    # Произношение
        5: (r'\{5\}', r'\{5\}'),    # Грамматические формы
        6: (r'\+6\+', r'\+6\+'),    # Иллюстрации
        7: (r'\{7\}', r'\{7\}'),    # Словообразование
        8: (r'\{8\}', r'\{8\}'),    # Словарные фиксации
        9: (r'\+9\+', r'\+9\+'),    # Синонимы
        10: (r'\+10\+', r'\+10\+'), # Антонимы
        11: (r'\{11\}', r'\{11\}'), # Фразеология
        12: (r'\{12\}', r'\{12\}'), # Морфемика
        13: (r'\{13\}', r'\{13\}'), # Этимология
    }

    def __init__(self, input_dir: str = '/app/input',
                 output_dir: str = '/app/output',
                 logs_dir: str = '/app/logs'):
        """
        Инициализация парсера

        Args:
            input_dir: Директория с входными файлами
            output_dir: Директория для выходных файлов
            logs_dir: Директория для логов
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.logs_dir = Path(logs_dir)

        # Создаем директории если их нет
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Логи для разных типов
        self.errors_log = self.logs_dir / 'errors.log'
        self.links_log = self.logs_dir / 'links.log'

    def read_document(self, file_path: Path) -> str:
        """
        Читает Word документ и извлекает весь текст

        Args:
            file_path: Путь к файлу

        Returns:
            Текст документа
        """
        try:
            doc = Document(file_path)
            text_parts = []

            for paragraph in doc.paragraphs:
                text_parts.append(paragraph.text)

            return '\n'.join(text_parts)
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return ""

    def extract_articles(self, text: str) -> List[str]:
        """
        Извлекает отдельные статьи из текста

        Args:
            text: Текст документа

        Returns:
            Список статей
        """
        articles = []

        # Находим все статьи между # и ##
        pattern = r'#(.*?)##'
        matches = re.finditer(pattern, text, re.DOTALL)

        for match in matches:
            article_text = match.group(1).strip()
            if article_text:
                articles.append(article_text)

        return articles

    def is_reference_article(self, article_text: str) -> bool:
        """
        Проверяет, является ли статья ссылочной

        Args:
            article_text: Текст статьи

        Returns:
            True если статья ссылочная
        """
        # Ищем паттерн "См." или "См ."
        return bool(re.search(r'См\.?\s+', article_text, re.IGNORECASE))

    def log_reference(self, article_text: str):
        """Логирует ссылочную статью"""
        with open(self.links_log, 'a', encoding='utf-8') as f:
            f.write(f"{article_text}\n")

    def log_error(self, error_type: str, article_text: str):
        """Логирует ошибку парсинга"""
        with open(self.errors_log, 'a', encoding='utf-8') as f:
            f.write(f"[{error_type}] {article_text}\n")

    def clean_word(self, word: str) -> str:
        """
        Очищает слово от лишних символов

        Args:
            word: Исходное слово

        Returns:
            Очищенное слово
        """
        # Убираем все кроме букв и тире
        cleaned = re.sub(r'[^\w\-а-яА-ЯёЁ]', '', word)
        # Заменяем ё на е
        cleaned = cleaned.replace('ё', 'е').replace('Ё', 'Е')
        # Приводим к нижнему регистру
        cleaned = cleaned.lower()
        return cleaned

    def extract_word_variants(self, text: str) -> List[str]:
        """
        Извлекает варианты слова (с опциональными окончаниями)

        Args:
            text: Текст с возможными вариантами типа "слово(ся)"

        Returns:
            Список вариантов слова
        """
        variants = []

        # Паттерн для слов с опциональными частями в скобках
        optional_pattern = r'(\S+)\((\S+)\)'
        match = re.search(optional_pattern, text)

        if match:
            base = match.group(1)
            optional = match.group(2)
            variants.append(base)
            variants.append(base + optional)
        else:
            variants.append(text)

        return variants

    def parse_section(self, text: str, section_type: int) -> Dict:
        """
        Парсит секцию

        Args:
            text: Текст секции
            section_type: Тип секции (0-13)

        Returns:
            Словарь с данными секции
        """
        section_data = {
            'type': section_type,
            'content': self.format_content(text),
            'sections': []
        }

        # Ищем вложенные секции
        for tag_type, (start_tag, end_tag) in self.TAG_PATTERNS.items():
            pattern = f'{start_tag}(.*?){end_tag}'
            matches = list(re.finditer(pattern, text))

            if matches:
                for match in matches:
                    nested_text = match.group(1)
                    nested_section = self.parse_section(nested_text, tag_type)
                    section_data['sections'].append(nested_section)

        return section_data

    def format_content(self, text: str) -> str:
        """
        Форматирует содержимое секции с HTML тегами

        Args:
            text: Исходный текст

        Returns:
            Отформатированный текст
        """
        # Базовое форматирование
        # Курсив для служебных слов
        formatted = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)

        # Жирный для заголовков (в секции 1)
        # formatted = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', formatted)

        return formatted

    def parse_article(self, article_text: str) -> Optional[Dict]:
        """
        Парсит одну статью

        Args:
            article_text: Текст статьи

        Returns:
            Словарь с данными статьи или None при ошибке
        """
        try:
            # Проверяем на ссылочную статью
            if self.is_reference_article(article_text):
                self.log_reference(article_text)
                return None

            article_data = {
                'writings': [],
                'sections': []
            }

            # Извлекаем все секции
            remaining_text = article_text
            position = 0

            # Парсим секции
            for tag_type, (start_tag, end_tag) in self.TAG_PATTERNS.items():
                pattern = f'{start_tag}(.*?){end_tag}'

                for match in re.finditer(pattern, article_text):
                    section_text = match.group(1).strip()
                    section = self.parse_section(section_text, tag_type)
                    article_data['sections'].append(section)

                    # Для секции 1 извлекаем слова
                    if tag_type == 1:
                        # Убираем верхние индексы (типа ¹, ²)
                        clean_text = re.sub(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+', '', section_text)

                        # Извлекаем варианты слова
                        word_variants = self.extract_word_variants(clean_text)

                        for variant in word_variants:
                            word = self.clean_word(variant)
                            if word:
                                writing = {
                                    'word': word,
                                    'value': variant.strip()
                                }
                                # Избегаем дубликатов
                                if writing not in article_data['writings']:
                                    article_data['writings'].append(writing)

                    # Удаляем обработанный текст
                    remaining_text = remaining_text.replace(match.group(0), '', 1)

            # Обрабатываем оставшийся текст как секцию 0
            remaining_text = remaining_text.strip()
            if remaining_text:
                section_0 = {
                    'type': 0,
                    'content': self.format_content(remaining_text),
                    'sections': []
                }
                article_data['sections'].append(section_0)

            return article_data if article_data['writings'] else None

        except Exception as e:
            logger.error(f"Ошибка парсинга статьи: {e}")
            self.log_error("PARSE_ERROR", article_text)
            return None

    def parse_document(self, file_path: Path) -> List[Dict]:
        """
        Парсит весь документ

        Args:
            file_path: Путь к файлу

        Returns:
            Список распарсенных статей
        """
        logger.info(f"Начинаем парсинг файла: {file_path}")

        # Читаем документ
        text = self.read_document(file_path)

        if not text:
            logger.warning(f"Файл {file_path} пустой или не читается")
            return []

        # Извлекаем статьи
        articles = self.extract_articles(text)
        logger.info(f"Найдено статей: {len(articles)}")

        # Парсим каждую статью
        results = []
        for i, article_text in enumerate(articles, 1):
            logger.debug(f"Парсинг статьи {i}/{len(articles)}")
            parsed = self.parse_article(article_text)
            if parsed:
                results.append(parsed)

        logger.info(f"Успешно распарсено статей: {len(results)}")
        return results

    def save_results(self, results: List[Dict], output_file: Path):
        """
        Сохраняет результаты в JSON файл

        Args:
            results: Список распарсенных статей
            output_file: Путь к выходному файлу
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Результаты сохранены в: {output_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения результатов: {e}")

    def process_all_documents(self):
        """Обрабатывает все документы в input директории"""
        if not self.input_dir.exists():
            logger.error(f"Директория {self.input_dir} не существует")
            return

        # Находим все .docx файлы
        docx_files = list(self.input_dir.glob('*.docx'))

        if not docx_files:
            logger.warning(f"Не найдено .docx файлов в {self.input_dir}")
            return

        logger.info(f"Найдено файлов для обработки: {len(docx_files)}")

        for docx_file in docx_files:
            # Пропускаем временные файлы Word
            if docx_file.name.startswith('~$'):
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"Обработка файла: {docx_file.name}")
            logger.info(f"{'='*60}")

            # Парсим документ
            results = self.parse_document(docx_file)

            # Сохраняем результаты
            output_file = self.output_dir / f"{docx_file.stem}.json"
            self.save_results(results, output_file)

        logger.info(f"\n{'='*60}")
        logger.info("Обработка завершена!")
        logger.info(f"Результаты в: {self.output_dir}")
        logger.info(f"Логи в: {self.logs_dir}")
        logger.info(f"{'='*60}")


def main():
    """Главная функция"""
    parser = DictionaryParser()
    parser.process_all_documents()


if __name__ == '__main__':
    main()
