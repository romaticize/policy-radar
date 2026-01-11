// ============================================================
// CONTENT FILTER MODULE
// Filters out exam prep, career advice, and non-policy content
// ============================================================

const ContentFilter = {
    
    // URL patterns that indicate non-policy content
    URL_EXCLUDE_PATTERNS: [
        /\/education\/competitive-exams\//i,
        /\/education\/upsc-/i,
        /\/education\/features\/jee/i,
        /\/education\/features\/neet/i,
        /\/education\/exam-/i,
        /\/career\//i,
        /\/internship/i,
        /\/college-review/i,
        /\/law-school-review/i,
        /\/campus-/i,
        /\/placement/i,
        /\/admission/i,
        /\/scholarship/i,
        /previous-year-paper/i,
        /question-paper/i,
        /answer-key/i,
        /exam-date/i,
        /exam-schedule/i,
        /exam-calendar/i,
        /syllabus-/i,
        /-syllabus\//i,
        /mock-test/i,
        /test-series/i,
        /preparation-strateg/i,
        /preparation-tips/i,
        /study-material/i,
        /current-affairs-quiz/i,
        /daily-news-summar/i,
    ],
    
    // Title keywords for exam/career content (case insensitive)
    EXAM_KEYWORDS: [
        // Exam names
        'upsc', 'ugc net', 'ugc-net', 'ssc cgl', 'ssc chsl', 'ssc je', 'ssc gd',
        'rrb je', 'rrb ntpc', 'neet', 'jee main', 'jee advanced', 'gate exam',
        'cat exam', 'clat', 'ailet', 'lsat', 'cuet', 'nta exam', 'swayam exam',
        'cbse board', 'icse board', 'state board exam',
        
        // Exam-related terms
        'exam calendar', 'exam schedule', 'exam date', 'exam notification',
        'admit card', 'hall ticket', 'answer key', 'result declared',
        'cut off', 'cutoff marks', 'merit list', 'rank list',
        'previous year paper', 'previous year question', 'pyq',
        'mock test', 'test series', 'practice paper', 'sample paper',
        'solved paper', 'model paper', 'question bank',
        'syllabus release', 'syllabus out', 'syllabus pdf',
        'preparation strateg', 'preparation tips', 'how to prepare',
        'study material', 'study plan', 'revision', 'crash course',
        'topper interview', 'topper strateg', 'rank holder',
        'current affairs quiz', 'daily current affairs', 'weekly current affairs',
        'gk questions', 'general knowledge', 'daily news summary',
        
        // Career/education (non-policy)
        'internship experience', 'internship opportunit', 'internship at',
        'law school review', 'college review', 'campus review',
        'placement drive', 'placement record', 'campus placement',
        'admission open', 'admission process', 'how to apply',
        'scholarship for', 'fellowship program',
        'career guidance', 'career option', 'career after',
    ],
    
    // Sources that primarily publish non-policy content
    NON_POLICY_SOURCES: [
        'lawctopus',
        'ipleaders',
        'legallyindia',
        'lawoktopus',
        'clatapult',
        'toprankers',
        'byjus',
        'unacademy',
        'testbook',
        'adda247',
        'gradeup',
        'careerlauncher',
        'timesofindia.indiatimes.com/education',
        'hindustantimes.com/education',
        'indianexpress.com/education',
        'ndtv.com/education',
        'news18.com/education',
    ],
    
    // Sources where we only want actual legal news (not career content)
    LEGAL_NEWS_ONLY_SOURCES: [
        'barandbench',
        'livelaw',
        'scconline',
        'legalbites',
    ],
    
    // Check if URL matches exclude patterns
    isExcludedUrl(url) {
        if (!url) return false;
        return this.URL_EXCLUDE_PATTERNS.some(pattern => pattern.test(url));
    },
    
    // Check if title contains exam keywords
    hasExamKeywords(title) {
        if (!title) return false;
        const lowerTitle = title.toLowerCase();
        return this.EXAM_KEYWORDS.some(kw => lowerTitle.includes(kw.toLowerCase()));
    },
    
    // Check if source is non-policy focused
    isNonPolicySource(sourceName, url) {
        const lowerSource = (sourceName || '').toLowerCase();
        const lowerUrl = (url || '').toLowerCase();
        
        return this.NON_POLICY_SOURCES.some(src => 
            lowerSource.includes(src) || lowerUrl.includes(src)
        );
    },
    
    // Main filter function
    shouldExclude(article) {
        const { title, url, source_name } = article;
        
        // 1. Check URL patterns first (most reliable)
        if (this.isExcludedUrl(url)) {
            return true;
        }
        
        // 2. Check if from non-policy source
        if (this.isNonPolicySource(source_name, url)) {
            // For these sources, be more strict
            // Only allow if it's clearly about policy/law changes
            const policyIndicators = [
                'supreme court', 'high court', 'bench', 'verdict', 'judgment',
                'parliament', 'lok sabha', 'rajya sabha', 'bill passed', 'act amended',
                'government', 'ministry', 'notification', 'circular', 'guideline',
                'regulation', 'policy change', 'cabinet', 'ordinance'
            ];
            
            const lowerTitle = (title || '').toLowerCase();
            const hasPolicyContent = policyIndicators.some(ind => lowerTitle.includes(ind));
            
            if (!hasPolicyContent) {
                return true;
            }
        }
        
        // 3. Check title for exam keywords
        if (this.hasExamKeywords(title)) {
            return true;
        }
        
        return false;
    },
    
    // Filter an array of articles
    filterArticles(articles) {
        return articles.filter(article => !this.shouldExclude(article));
    }
};

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ContentFilter;
}
