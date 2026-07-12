/** 与后端 word_estimate / generation-config 对齐的页数字数换算 */

export function formatWordsDisplay(totalWords) {
  if (totalWords >= 10000) return `${(totalWords / 10000).toFixed(2)}万字`;
  return `${totalWords}字`;
}

export function buildPagesEstimate(pages, wordsPerPage = 780) {
  const estimatedPages = Math.max(1, Number(pages) || 1);
  const wpp = Number(wordsPerPage) || 780;
  const totalWords = estimatedPages * wpp;
  return {
    estimated_pages: estimatedPages,
    total_words: totalWords,
    display_words: formatWordsDisplay(totalWords),
    words_per_page: wpp,
    target_pages: estimatedPages,
  };
}

export function estimatePagesFromWords(totalWords, wordsPerPage = 780) {
  const wpp = Number(wordsPerPage) || 780;
  const words = Number(totalWords) || 0;
  return words > 0 ? Math.max(1, Math.round(words / wpp)) : 0;
}
