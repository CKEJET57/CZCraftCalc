// src/utils/rankColors.ts

export const RANK_TEXT_COLORS: Record<string, string> = {

  RANK_COMMON: '#EEEEEE',       // Обычный (Белый)
  RANK_UNCOMMON: '#5EDB5E',     // Необычный (Зеленый)
  RANK_RARE: '#BD6AFF',         // Редкий (Фиолетовый)
  RANK_LEGENDARY: '#FFB000',    // Легендарный (Оранжевый/Золотой)
  RANK_EXCEPTIONAL: '#FF4C4C',  // Исключительный (Красный)
  RANK_SPECIAL: '#00D0FF',      // Особый (Голубой)
  
  DEFAULT: '#EEEEEE',           // Отмычка
  RANK_NEWBIE: '#5EDB5E',       // Новичок
  RANK_STALKER: '#1167e9',      // Сталкер
  RANK_VETERAN: '#BD6AFF',      // Ветеран
  RANK_MASTER: '#FF4C4C',       // Мастер
  RANK_LEGEND: '#FFB000',       // Легенда
};

// Функция для безопасного получения цвета
export function getRankColor(rank?: string): string {
  if (!rank) return '#FFFFFF'; // Цвет по умолчанию
  // Если в JSON придет 'RANK_STALKER', вернется цвет, если нет — белый
  return RANK_TEXT_COLORS[rank] || '#FFFFFF'; 
}