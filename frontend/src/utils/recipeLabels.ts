// src/utils/recipeLabels.ts

/**
 * Словарь навыков (перков) из поля `requirements.perks`
 */
export const PERK_LABELS: Record<string, string> = {
  ammunition: 'Боеприпасы',
  pyrotechnics: 'Пиротехника',
  armorer: 'Защитное снаряжение',
  engineering: 'Инженерия',
  cooking: 'Кулинария',
  brewing: 'Самогоноварение',
  medicine: 'Медицина',
  materials: 'Сырье и материалы',
};

/**
 * Словарь станков и инструментов из полей `bench` и `requirements.features`
 */
export const FEATURE_LABELS: Record<string, string> = {
  // Станки
  workbench: 'Верстак',
  laboratory_table: 'Лабораторный стол',
  kitchen_table: 'Кухонный стол',

  // Инструменты и электроника
  precise_tools: 'Прецизионный инструментарий',
  precise_powertools: 'Точные электроинструменты',
  tool_trolley: 'Тележка с инструментами',
  wrenches_kit: 'Набор гаечных ключей',
  screwdrivers: 'Набор отверток и щипцов',
  electronics_kit: 'Набор для работы с электроникой',
  calipers_kit: 'Набор штангенциркулей',
  laser_level: 'Лазерный уровень',
  scalpels_kit: 'Набор скальпелей',

  // Тяжелое оборудование
  cnc: 'ЧПУ',
  lathe: 'Токарный станок',
  welding_equipment: 'Сварочное оборудование',
  chemical_reactor: 'Химический реактор',
  centrifuge: 'Центрифуга',
  rotary_evaporator: 'Роторная система',
  chromatographic_equipment: 'Хроматографическое оборудование',
  laminar_box: 'Ламинарный бокс',
  sterilization_system: 'Система стерилизации',
  fermentation_container: 'Тара для брожения',

  // Кухня и лабораторная утварь
  flasks_kit: 'Набор колб и мензурок',
  gauze_filter: 'Фильтр из марли',
  hoods: 'Вытяжка',
  stove: 'Кухонная плита',
  water_collector: 'Водосборник',
  kitchen_items: 'Кухонная утварь',

  // Энергия
  generator_energy_source_battery: 'Станция для приема батарей',
  generator_energy_source_anomal: 'Станция аномального преобразования',
};

/**
 * Возвращает русское название навыка по его системному ключу.
 * Если ключ не найден, возвращает исходную строку.
 */
export function getPerkLabel(key: string): string {
  if (!key) return '';
  return PERK_LABELS[key] || key;
}

/**
 * Возвращает русское название оборудования по его системному ключу.
 * Если ключ не найден, возвращает исходную строку.
 */
export function getFeatureLabel(key: string): string {
  if (!key) return '';
  return FEATURE_LABELS[key] || key;
}