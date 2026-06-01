// Core scanning logic to analyze job postings
export const analyzeJobText = (text, scamKeywords, verifiedCompanies) => {
  if (!text) return { score: 0, flags: [], status: 'unknown' };

  let score = 100;
  const flags = [];
  const textLower = text.toLowerCase();

  // 1. Check for scam keywords
  for (const keyword of scamKeywords) {
    if (textLower.includes(keyword.term.toLowerCase())) {
      score -= keyword.weight;
      flags.push({
        type: 'warning',
        message: `Found suspicious phrase: "${keyword.term}"`,
        description: keyword.description
      });
    }
  }

  // 2. Check for missing information (e.g., salary, company name)
  // Simplified for now
  if (!textLower.includes('salary') && !textLower.includes('pay')) {
    score -= 10;
    flags.push({
      type: 'info',
      message: 'No salary information provided',
      description: 'Legitimate jobs usually mention salary or compensation.'
    });
  }

  // Determine status based on score
  let status = 'safe';
  if (score < 40) status = 'danger';
  else if (score < 70) status = 'warning';

  return {
    score: Math.max(0, score),
    flags,
    status
  };
};
