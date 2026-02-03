#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Парсер словарных статей из Word документов
Обрабатывает специальные теги и извлекает структурированные данные
"""

import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from docx import Document


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DictionaryParser:
    """Парсер словарных статей согласно спецификации parsing.md"""

    # Паттерны для тегов секций
    TAG_PATTERNS = {
        1: (r'\{1\}', r'\{1\}'),
        2: (r'\{2\}', r'\{2\}'),
        3: (r'\{3\}', r'\{3\}'),
        4: (r'\{4\}', r'\{4\}'),
        5: (r'\{5\}', r'\{5\}'),
        6: (r'\+6\+', r'\+6\+'),
        7: (r'\{7\}', r'\{7\}'),
        8: (r'\{8\}', r'\{8\}'),
        9: (r'\+9\+', r'\+9\+'),
        10: (r'\+10\+', r'\+10\+'),
        11: (r'\{11\}', r'\{11\}'),
        12: (r'\{12\}', r'\{12\}'),
        13: (r'\{13\}', r'\{13\}'),
    }

    def __init__(self, input_dir: str = '/app/input',
                 output_dir: str = '/app/output',
                 logs_dir: str = '/app/logs'):
        """Инициализация парсера"""
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.logs_dir = Path(logs_dir)

        # Создаем директории
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Файлы логов
        self.errors_log = self.logs_dir / 'errors.log'
        self.links_log = self.logs_dir / 'links.log'

        # Список для накопления блоков с ошибками
        self.error_blocks = []

    def read_document(self, file_path: Path) -> str:
        """Читает Word документ и возвращает текст"""
        try:
            doc = Document(file_path)
            text_parts = []
            for paragraph in doc.paragraphs:
                text_parts.append(paragraph.text)
            return ''.join(text_parts)
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return ""

    def extract_articles(self, text: str) -> List[str]:
        """Извлекает статьи между # и ##"""
        articles = []
        pattern = r'#(.*?)##'
        matches = re.finditer(pattern, text, re.DOTALL)

        for match in matches:
            article_text = match.group(1)
            if article_text.strip():
                articles.append(article_text)

        return articles

    def is_reference_article(self, article_text: str) -> bool:
        """
        Проверяет, является ли статья ссылочной (типа "СЛОВО. См. Другое_слово")
        Ссылочная статья должна содержать 'См.' в начале после заголовка
        """
        # Убираем секцию 1 (заголовок) и проверяем, начинается ли оставшееся с "См."
        # Паттерн: {1}ЗАГОЛОВОК{1}. См. ИЛИ {1}ЗАГОЛОВОК{1}, См. ИЛИ просто {1}ЗАГОЛОВОК{1} См.
        pattern = r'\{1\}[^\}]+\{1\}\s*[,\.\s]*\s*См\.\s+'
        return bool(re.match(pattern, article_text, re.IGNORECASE))

    def log_reference(self, article_text: str):
        """Логирует ссылочную статью"""
        with open(self.links_log, 'a', encoding='utf-8') as f:
            f.write(f"#{article_text}##\n")
        logger.info("Найдена ссылочная статья")

    def log_error(self, error_type: str, article_text: str, details: str = ""):
        """Логирует ошибку парсинга и добавляет в список блоков с ошибками"""
        # Записываем в текстовый лог (старый способ)
        with open(self.errors_log, 'a', encoding='utf-8') as f:
            f.write(f"[{error_type}] {details}\n#{article_text}##\n\n")

        # Добавляем в список блоков с ошибками для JSON
        error_entry = {
            'type': error_type,
            'message': details
        }

        # Формируем полный текст блока с маркерами
        full_block_text = f'#{article_text}##'

        # Проверяем, есть ли уже этот блок в списке
        existing_block = None
        for block in self.error_blocks:
            if block['block'] == full_block_text:
                existing_block = block
                break

        if existing_block:
            # Добавляем ошибку к существующему блоку
            existing_block['errors'].append(error_entry)
        else:
            # Создаем новый блок с ошибкой
            self.error_blocks.append({
                'block': full_block_text,
                'errors': [error_entry]
            })

        logger.warning(f"Ошибка парсинга: {error_type}")

    def clean_word(self, word: str) -> str:
        """
        Очищает слово:
        - Только буквы и тире
        - ё -> е
        - Нижний регистр
        """
        # Убираем всё кроме букв и тире
        cleaned = re.sub(r'[^\wа-яА-ЯёЁ\-]', '', word, flags=re.UNICODE)
        # ё -> е
        cleaned = cleaned.replace('ё', 'е').replace('Ё', 'Е')
        # Нижний регистр
        cleaned = cleaned.lower()
        return cleaned

    def extract_word_variants(self, text: str) -> List[Dict[str, str]]:
        """
        Извлекает варианты слов из текста секции 1
        Обрабатывает опциональные окончания типа слово(ся)
        Согласно спецификации п.4: "Написание сохраняем как есть, но все буквы переводим в нижний регистр"
        """
        variants = []

        # Удаляем числовые верхние индексы
        text = re.sub(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+', '', text)

        # Паттерн для слов с опциональными частями в скобках
        optional_pattern = r'([^\s\(\)]+)\(([^\)]+)\)'

        # Ищем все вхождения с опциональными частями
        for match in re.finditer(optional_pattern, text):
            base = match.group(1)
            optional = match.group(2)

            # Вариант без опционального окончания
            word_without = self.clean_word(base)
            if word_without:
                variants.append({
                    'word': word_without,
                    'value': base.lower()  # Нижний регистр для value
                })

            # Вариант с опциональным окончанием
            word_with = self.clean_word(base + optional)
            if word_with:
                variants.append({
                    'word': word_with,
                    'value': (base + optional).lower()  # Нижний регистр для value
                })

            # Удаляем обработанный текст
            text = text.replace(match.group(0), '', 1)

        # Обрабатываем оставшиеся слова (без опциональных частей)
        # Разбиваем по пробелам и извлекаем слова
        words = re.findall(r'[^\s\(\)]+', text)
        for word_text in words:
            word_text = word_text.strip()
            if word_text and not re.match(r'^[\,\.\;\:\!\?]$', word_text):
                cleaned = self.clean_word(word_text)
                if cleaned:
                    variants.append({
                        'word': cleaned,
                        'value': word_text.lower()  # Нижний регистр для value
                    })

        return variants

    def normalize_html_tags(self, content: str) -> str:
        """
        Нормализует HTML теги согласно спецификации:
        - <b> -> <strong>
        - <i> -> <em>
        - Закрывает незакрытые теги
        - Открывает закрытые без открытия теги
        """
        # Заменяем <b> на <strong>
        content = re.sub(r'<b(\s[^>]*)?>',  r'<strong\1>', content, flags=re.IGNORECASE)
        content = re.sub(r'</b>', '</strong>', content, flags=re.IGNORECASE)

        # Заменяем <i> на <em>
        content = re.sub(r'<i(\s[^>]*)?>',  r'<em\1>', content, flags=re.IGNORECASE)
        content = re.sub(r'</i>', '</em>', content, flags=re.IGNORECASE)

        # Находим все открывающие и закрывающие теги
        opening_tags = re.findall(r'<(strong|em)(\s[^>]*)?>', content, re.IGNORECASE)
        closing_tags = re.findall(r'</(strong|em)>', content, re.IGNORECASE)

        # Подсчитываем теги
        tag_stack = []
        for tag_name, attrs in opening_tags:
            tag_stack.append(tag_name.lower())

        for tag_name in closing_tags:
            tag_name = tag_name.lower()
            if tag_stack and tag_stack[-1] == tag_name:
                tag_stack.pop()
            else:
                # Закрывающий тег без открывающего - добавляем открывающий в начало
                content = f'<{tag_name}>{content}'

        # Закрываем все незакрытые теги в конце
        while tag_stack:
            tag_name = tag_stack.pop()
            content = f'{content}</{tag_name}>'

        return content

    def format_content(self, content: str, section_type: int) -> str:
        """
        Форматирует контент с HTML тегами
        - Курсив (_текст_) -> <em>текст</em>
        - Для секции 1: контент -> <strong>контент</strong>
        - Нормализует HTML теги (b->strong, i->em)
        """
        # Заменяем _текст_ на <em>текст</em>
        formatted = re.sub(r'_([^_]+)_', r'<em>\1</em>', content)

        # Нормализуем HTML теги
        formatted = self.normalize_html_tags(formatted)

        # Для секции 1 оборачиваем в <strong>
        if section_type == 1:
            formatted = f'<strong>{formatted}</strong>'

        return formatted

    def find_all_tags(self, text: str) -> List[Tuple[int, int, int, str]]:
        """
        Находит все теги в тексте и возвращает список (start_pos, end_pos, type, content)
        отсортированный по позиции начала
        """
        tags = []

        for tag_type, (start_pattern, end_pattern) in self.TAG_PATTERNS.items():
            # Ищем все вхождения пары тегов
            pattern = f'{start_pattern}(.*?){end_pattern}'
            for match in re.finditer(pattern, text, re.DOTALL):
                start_pos = match.start()
                end_pos = match.end()
                content = match.group(1)
                tags.append((start_pos, end_pos, tag_type, content))

        # Сортируем по позиции начала
        tags.sort(key=lambda x: x[0])

        return tags

    def filter_top_level_tags(self, tags: List[Tuple[int, int, int, str]]) -> List[Tuple[int, int, int, str]]:
        """
        Фильтрует теги, оставляя только теги верхнего уровня (не вложенные)
        """
        if not tags:
            return []

        top_level = []
        for i, (start, end, tag_type, content) in enumerate(tags):
            # Проверяем, не находится ли этот тег внутри другого
            is_nested = False
            for j, (other_start, other_end, other_type, other_content) in enumerate(tags):
                if i != j and other_start < start and end < other_end:
                    # Этот тег находится внутри другого
                    is_nested = True
                    break

            if not is_nested:
                top_level.append((start, end, tag_type, content))

        return top_level

    def parse_nested_sections(self, content: str) -> List[Dict]:
        """
        Парсит вложенные секции внутри контента
        Разбивает контент на подсекции:
        - Текст между вложенными секциями становится секцией типа 0
        - Вложенные секции сохраняются со своим типом
        Возвращает список секций
        """
        nested_sections = []

        # Находим все вложенные теги
        nested_tags = self.find_all_tags(content)

        if not nested_tags:
            return []

        last_pos = 0

        for start_pos, end_pos, tag_type, nested_content in nested_tags:
            # Текст перед вложенной секцией (секция 0)
            if start_pos > last_pos:
                text_before = content[last_pos:start_pos]
                if text_before.strip() or text_before:  # Сохраняем даже пробелы
                    nested_sections.append({
                        'type': 0,
                        'content': self.format_content(text_before, 0)
                    })

            # Вложенная секция
            nested_sections.append({
                'type': tag_type,
                'content': self.format_content(nested_content, tag_type)
            })

            last_pos = end_pos

        # Текст после последней вложенной секции (секция 0)
        if last_pos < len(content):
            text_after = content[last_pos:]
            if text_after.strip() or text_after:  # Сохраняем даже пробелы
                nested_sections.append({
                    'type': 0,
                    'content': self.format_content(text_after, 0)
                })

        return nested_sections

    def parse_article_sections(self, article_text: str) -> Tuple[List[Dict], List[Dict[str, str]]]:
        """
        Парсит секции статьи, сохраняя порядок
        Возвращает (sections, writings)

        Важно: Секции с вложенными подсекциями имеют только поле 'sections',
        секции без вложенных имеют только поле 'content'
        """
        sections = []
        writings = []

        # Находим все теги и фильтруем, оставляя только верхнего уровня
        all_tags = self.find_all_tags(article_text)
        tags = self.filter_top_level_tags(all_tags)

        if not tags:
            # Если нет тегов, вся статья - секция 0
            sections.append({
                'type': 0,
                'content': self.format_content(article_text, 0)
            })
            return sections, writings

        # Обрабатываем текст между тегами
        last_pos = 0

        for start_pos, end_pos, tag_type, content in tags:
            # Текст перед тегом (секция 0)
            if start_pos > last_pos:
                text_between = article_text[last_pos:start_pos]
                if text_between.strip() or text_between:  # Сохраняем даже пробелы
                    sections.append({
                        'type': 0,
                        'content': self.format_content(text_between, 0)
                    })

            # Парсим вложенные секции
            nested_sections = self.parse_nested_sections(content)

            # Создаем секцию
            if nested_sections:
                # Секция с вложенными: только 'sections', БЕЗ 'content'
                section = {
                    'type': tag_type,
                    'sections': nested_sections
                }
            else:
                # Секция без вложенных: только 'content', БЕЗ 'sections'
                section = {
                    'type': tag_type,
                    'content': self.format_content(content, tag_type)
                }

            sections.append(section)

            # Для секции 1 извлекаем слова
            if tag_type == 1:
                word_variants = self.extract_word_variants(content)
                writings.extend(word_variants)

            last_pos = end_pos

        # Текст после последнего тега (секция 0)
        if last_pos < len(article_text):
            text_after = article_text[last_pos:]
            if text_after.strip() or text_after:  # Сохраняем даже пробелы
                sections.append({
                    'type': 0,
                    'content': self.format_content(text_after, 0)
                })

        # Убираем дубликаты из writings
        unique_writings = []
        seen = set()
        for w in writings:
            key = (w['word'], w['value'])
            if key not in seen:
                seen.add(key)
                unique_writings.append(w)

        return sections, unique_writings

    def parse_article(self, article_text: str) -> Optional[Dict]:
        """Парсит одну статью"""
        try:
            # Проверяем на ссылочную статью
            if self.is_reference_article(article_text):
                self.log_reference(article_text)
                return None

            # Парсим секции
            sections, writings = self.parse_article_sections(article_text)

            if not writings and not sections:
                self.log_error("EMPTY_ARTICLE", article_text, "Статья не содержит данных")
                return None

            return {
                'writings': writings,
                'sections': sections
            }

        except Exception as e:
            logger.error(f"Ошибка парсинга статьи: {e}")
            self.log_error("PARSE_ERROR", article_text, str(e))
            return None

    def parse_document(self, file_path: Path) -> List[Dict]:
        """Парсит весь документ"""
        logger.info(f"Начинаем парсинг файла: {file_path.name}")

        # Очищаем список блоков с ошибками перед обработкой нового документа
        self.error_blocks = []

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
        """Сохраняет результаты в JSON"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Результаты сохранены в: {output_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения результатов: {e}")

    def save_error_blocks(self, output_file: Path):
        """Сохраняет блоки с ошибками в отдельный JSON файл"""
        if not self.error_blocks:
            logger.info("Нет блоков с ошибками для сохранения")
            return

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.error_blocks, f, ensure_ascii=False, indent=2)
            logger.info(f"Блоки с ошибками сохранены в: {output_file}")
            logger.info(f"Всего блоков с ошибками: {len(self.error_blocks)}")
        except Exception as e:
            logger.error(f"Ошибка сохранения блоков с ошибками: {e}")

    def process_all_documents(self):
        """Обрабатывает все документы в input директории"""
        if not self.input_dir.exists():
            logger.error(f"Директория {self.input_dir} не существует")
            return

        # Находим все .docx файлы
        docx_files = list(self.input_dir.glob('*.docx'))

        # Фильтруем временные файлы Word
        docx_files = [f for f in docx_files if not f.name.startswith('~$')]

        if not docx_files:
            logger.warning(f"Не найдено .docx файлов в {self.input_dir}")
            return

        logger.info(f"Найдено файлов для обработки: {len(docx_files)}")

        for docx_file in docx_files:
            logger.info(f"\n{'='*60}")
            logger.info(f"Обработка файла: {docx_file.name}")
            logger.info(f"{'='*60}")

            # Парсим документ
            results = self.parse_document(docx_file)

            # Сохраняем результаты
            output_file = self.output_dir / f"{docx_file.stem}.json"
            self.save_results(results, output_file)

            # Сохраняем блоки с ошибками
            errors_output_file = self.output_dir / f"{docx_file.stem}_errors.json"
            self.save_error_blocks(errors_output_file)

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
