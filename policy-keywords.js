/**
 * PolicyKeywords Module v6.2
 * Unified keyword extraction and normalization for PolicyRadar
 * 
 * Usage:
 *   <script src="policy-keywords.js"></script>
 *   const keywords = PolicyKeywords.extractFromArticles(articles);
 *   const normalized = PolicyKeywords.normalize("rbi governor");
 */

const PolicyKeywords = (function() {
    'use strict';
    
    // =========================================
    // KNOWN POLICY PHRASES (Multi-word terms)
    // =========================================
    const KNOWN_PHRASES = new Set([
        // Government Programs
        'digital india', 'make in india', 'startup india', 'skill india',
        'atmanirbhar bharat', 'swachh bharat', 'smart cities', 'pradhan mantri',
        'jan dhan', 'ujjwala yojana', 'ayushman bharat', 'pm kisan',
        'one nation one ration', 'one nation one tax', 'one nation one election',
        'atal pension yojana', 'sukanya samriddhi', 'stand up india',
        'bharat net', 'gram swaraj', 'ujala scheme', 'national highways',
        
        // Economic Terms
        'fiscal deficit', 'current account deficit', 'trade deficit',
        'foreign exchange', 'monetary policy', 'fiscal policy', 'repo rate',
        'reverse repo', 'cash reserve ratio', 'statutory liquidity ratio',
        'gross domestic product', 'gross value added', 'wholesale price index',
        'consumer price index', 'ease of doing business', 'foreign direct investment',
        'foreign institutional investor', 'public sector undertaking',
        'disinvestment', 'privatization', 'public private partnership',
        'capital gains', 'goods and services tax', 'income tax',
        'corporate tax', 'customs duty', 'excise duty', 'tax evasion',
        'black money', 'offshore accounts', 'tax haven',
        
        // Regulatory Bodies
        'reserve bank', 'finance ministry', 'commerce ministry',
        'external affairs ministry', 'home ministry', 'defence ministry',
        'prime minister office', 'cabinet secretary', 'attorney general',
        'solicitor general', 'comptroller auditor general', 'election commission',
        'central information commission', 'national green tribunal',
        'national company law tribunal', 'insolvency bankruptcy',
        'competition commission', 'consumer disputes',
        
        // Digital & Tech
        'digital public infrastructure', 'unified payments interface',
        'aadhaar enabled', 'open network', 'digital commerce', 'open banking',
        'account aggregator', 'central bank digital currency', 'blockchain',
        'artificial intelligence', 'machine learning', 'data protection',
        'personal data', 'data privacy', 'data localization', 'cross border',
        'data fiduciary', 'consent manager', 'data principal',
        'social media', 'intermediary guidelines', 'safe harbour',
        'significant social media intermediary', 'content moderation',
        
        // Labour & Employment
        'labour code', 'minimum wage', 'provident fund', 'gratuity',
        'industrial disputes', 'trade union', 'contract labour',
        'gig worker', 'platform worker', 'social security', 'esi',
        'epfo', 'pension fund', 'unorganized sector',
        
        // Infrastructure
        'national infrastructure pipeline', 'gati shakti', 'bharatmala',
        'sagarmala', 'dedicated freight corridor', 'high speed rail',
        'bullet train', 'metro rail', 'smart city', 'housing for all',
        'affordable housing', 'real estate', 'rera', 'infrastructure investment trust',
        
        // Energy & Environment
        'renewable energy', 'solar power', 'wind power', 'green hydrogen',
        'electric vehicle', 'carbon emission', 'net zero', 'climate change',
        'paris agreement', 'cop summit', 'national action plan',
        'clean energy', 'fossil fuel', 'coal mining', 'gas pipeline',
        
        // Healthcare
        'public health', 'medical device', 'drug pricing', 'essential medicines',
        'clinical trial', 'pharmaceutical', 'generic drug', 'vaccine',
        'health insurance', 'medical college', 'nursing', 'telemedicine',
        
        // Education
        'national education policy', 'higher education', 'skill development',
        'vocational training', 'digital literacy', 'online education',
        'school education', 'teacher training', 'national testing agency',
        
        // Legal & Governance
        'constitutional amendment', 'ordinance', 'parliament session',
        'lok sabha', 'rajya sabha', 'supreme court', 'high court',
        'district court', 'judicial review', 'public interest litigation',
        'fundamental rights', 'directive principles', 'article 370',
        'citizenship amendment', 'uniform civil code', 'anti defection',
        'governor role', 'president rule', 'emergency provisions',
        
        // Trade & Commerce
        'export promotion', 'import substitution', 'trade agreement',
        'free trade', 'world trade organization', 'most favoured nation',
        'anti dumping', 'countervailing duty', 'safeguard duty',
        'special economic zone', 'export processing zone',
        
        // Banking & Finance
        'non performing asset', 'asset reconstruction', 'bad bank',
        'bank merger', 'privatization', 'priority sector lending',
        'micro finance', 'small finance bank', 'payment bank',
        'cooperative bank', 'regional rural bank', 'development finance',
        'venture capital', 'angel investor', 'private equity',
        'initial public offering', 'follow on offer', 'rights issue',
        
        // Defense & Security
        'national security', 'border security', 'cyber security',
        'defence procurement', 'make in india defence', 'strategic partnership',
        'nuclear program', 'missile defense', 'armed forces',
        'paramilitary', 'counter terrorism', 'internal security',
        
        // Agriculture
        'minimum support price', 'agricultural produce marketing',
        'farmer producer organization', 'crop insurance', 'kisan credit',
        'agricultural infrastructure', 'cold storage', 'food processing',
        'organic farming', 'natural farming', 'food security',
    ]);
    
    // =========================================
    // KNOWN ACRONYMS
    // =========================================
    const ACRONYMS = {
        // Regulators
        'rbi': 'Reserve Bank of India',
        'sebi': 'Securities and Exchange Board of India',
        'irdai': 'Insurance Regulatory and Development Authority of India',
        'trai': 'Telecom Regulatory Authority of India',
        'pfrda': 'Pension Fund Regulatory and Development Authority',
        'ibbi': 'Insolvency and Bankruptcy Board of India',
        'cci': 'Competition Commission of India',
        'fssai': 'Food Safety and Standards Authority of India',
        'cbi': 'Central Bureau of Investigation',
        'ed': 'Enforcement Directorate',
        'ngt': 'National Green Tribunal',
        'nclt': 'National Company Law Tribunal',
        'nclat': 'National Company Law Appellate Tribunal',
        'cerc': 'Central Electricity Regulatory Commission',
        'aerc': 'Atomic Energy Regulatory Commission',
        
        // Government Bodies
        'mof': 'Ministry of Finance',
        'mha': 'Ministry of Home Affairs',
        'mea': 'Ministry of External Affairs',
        'mod': 'Ministry of Defence',
        'moef': 'Ministry of Environment and Forests',
        'meity': 'Ministry of Electronics and Information Technology',
        'dpiit': 'Department for Promotion of Industry and Internal Trade',
        'dgft': 'Directorate General of Foreign Trade',
        'cbdt': 'Central Board of Direct Taxes',
        'cbic': 'Central Board of Indirect Taxes and Customs',
        'niti': 'National Institution for Transforming India',
        'cag': 'Comptroller and Auditor General',
        'upsc': 'Union Public Service Commission',
        
        // Financial
        'gst': 'Goods and Services Tax',
        'gstn': 'Goods and Services Tax Network',
        'npa': 'Non-Performing Asset',
        'arc': 'Asset Reconstruction Company',
        'nbfc': 'Non-Banking Financial Company',
        'hfc': 'Housing Finance Company',
        'mf': 'Mutual Fund',
        'aif': 'Alternative Investment Fund',
        'fpi': 'Foreign Portfolio Investment',
        'fdi': 'Foreign Direct Investment',
        'ecb': 'External Commercial Borrowings',
        'adr': 'American Depositary Receipt',
        'gdr': 'Global Depositary Receipt',
        'ipo': 'Initial Public Offering',
        'fpo': 'Follow-on Public Offer',
        'ofs': 'Offer For Sale',
        'reit': 'Real Estate Investment Trust',
        'invit': 'Infrastructure Investment Trust',
        'etf': 'Exchange Traded Fund',
        'sip': 'Systematic Investment Plan',
        
        // Digital
        'upi': 'Unified Payments Interface',
        'imps': 'Immediate Payment Service',
        'neft': 'National Electronic Funds Transfer',
        'rtgs': 'Real Time Gross Settlement',
        'npci': 'National Payments Corporation of India',
        'bbps': 'Bharat Bill Payment System',
        'bhim': 'Bharat Interface for Money',
        'cbdc': 'Central Bank Digital Currency',
        'dpi': 'Digital Public Infrastructure',
        'ondc': 'Open Network for Digital Commerce',
        'ocen': 'Open Credit Enablement Network',
        'depa': 'Data Empowerment and Protection Architecture',
        'dpdp': 'Digital Personal Data Protection',
        'pdpb': 'Personal Data Protection Bill',
        'it act': 'Information Technology Act',
        'ai': 'Artificial Intelligence',
        'ml': 'Machine Learning',
        
        // Economic
        'gdp': 'Gross Domestic Product',
        'gva': 'Gross Value Added',
        'cpi': 'Consumer Price Index',
        'wpi': 'Wholesale Price Index',
        'iip': 'Index of Industrial Production',
        'pmi': 'Purchasing Managers Index',
        'cad': 'Current Account Deficit',
        'bop': 'Balance of Payments',
        'forex': 'Foreign Exchange',
        'crr': 'Cash Reserve Ratio',
        'slr': 'Statutory Liquidity Ratio',
        'msp': 'Minimum Support Price',
        'pds': 'Public Distribution System',
        
        // Social
        'epfo': 'Employees Provident Fund Organisation',
        'esic': 'Employees State Insurance Corporation',
        'pmjdy': 'Pradhan Mantri Jan Dhan Yojana',
        'pmjjby': 'Pradhan Mantri Jeevan Jyoti Bima Yojana',
        'pmsby': 'Pradhan Mantri Suraksha Bima Yojana',
        'pmay': 'Pradhan Mantri Awas Yojana',
        'pmuy': 'Pradhan Mantri Ujjwala Yojana',
        'mgnrega': 'Mahatma Gandhi National Rural Employment Guarantee Act',
        'nfsa': 'National Food Security Act',
        'ab': 'Ayushman Bharat',
        'pmjay': 'Pradhan Mantri Jan Arogya Yojana',
        
        // Infrastructure
        'nhai': 'National Highways Authority of India',
        'ril': 'Reliance Industries Limited',
        'ntpc': 'National Thermal Power Corporation',
        'ongc': 'Oil and Natural Gas Corporation',
        'iocl': 'Indian Oil Corporation Limited',
        'bpcl': 'Bharat Petroleum Corporation Limited',
        'hpcl': 'Hindustan Petroleum Corporation Limited',
        'gail': 'Gas Authority of India Limited',
        'sez': 'Special Economic Zone',
        'dfc': 'Dedicated Freight Corridor',
        'hsrl': 'High Speed Rail Link',
        
        // Defence
        'drdo': 'Defence Research and Development Organisation',
        'isro': 'Indian Space Research Organisation',
        'hal': 'Hindustan Aeronautics Limited',
        'bel': 'Bharat Electronics Limited',
        'bdl': 'Bharat Dynamics Limited',
        'beml': 'Bharat Earth Movers Limited',
        'oem': 'Original Equipment Manufacturer',
        
        // Organizations
        'bse': 'Bombay Stock Exchange',
        'nse': 'National Stock Exchange',
        'nsdl': 'National Securities Depository Limited',
        'cdsl': 'Central Depository Services Limited',
        'ifc': 'International Finance Corporation',
        'imf': 'International Monetary Fund',
        'wb': 'World Bank',
        'adb': 'Asian Development Bank',
        'aiib': 'Asian Infrastructure Investment Bank',
        'ndb': 'New Development Bank',
        'wto': 'World Trade Organization',
        'rcep': 'Regional Comprehensive Economic Partnership',
        'brics': 'Brazil Russia India China South Africa',
        'saarc': 'South Asian Association for Regional Cooperation',
        'asean': 'Association of Southeast Asian Nations',
        'g20': 'Group of Twenty',
        'quad': 'Quadrilateral Security Dialogue',
    };
    
    // =========================================
    // ENHANCED STOPWORDS (Indian English)
    // =========================================
    const STOPWORDS = new Set([
        // Standard English
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'that', 'which', 'who', 'whom', 'this', 'these', 'those', 'it', 'its',
        'not', 'no', 'nor', 'so', 'than', 'too', 'very', 'just', 'also',
        'only', 'even', 'more', 'most', 'other', 'some', 'any', 'all',
        'each', 'every', 'both', 'few', 'many', 'much', 'such', 'own',
        'same', 'about', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'between', 'under', 'again', 'further', 'then',
        'once', 'here', 'there', 'when', 'where', 'why', 'how', 'what',
        'if', 'because', 'until', 'while', 'although', 'though', 'unless',
        'whether', 'yet', 'however', 'therefore', 'thus', 'hence',
        'being', 'having', 'doing', 'going', 'coming', 'getting',
        
        // News/reporting terms
        'said', 'says', 'told', 'added', 'noted', 'stated', 'according',
        'report', 'reports', 'reported', 'reporting', 'news', 'article',
        'sources', 'officials', 'official', 'spokesperson', 'announcement',
        'announced', 'statement', 'statements', 'mentioned', 'claimed',
        'revealed', 'disclosed', 'confirmed', 'denied', 'alleged',
        'update', 'updates', 'updated', 'latest', 'recent', 'new',
        'today', 'yesterday', 'tomorrow', 'week', 'month', 'year',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        
        // Indian English specific
        'lakh', 'lakhs', 'crore', 'crores', 'rupee', 'rupees', 'rs', 'inr',
        'per', 'cent', 'percent', 'percentage',
        'govt', 'government', 'central', 'state', 'union', 'national',
        
        // Major Indian cities (usually not keywords)
        'delhi', 'mumbai', 'kolkata', 'chennai', 'bangalore', 'bengaluru',
        'hyderabad', 'ahmedabad', 'pune', 'jaipur', 'lucknow', 'kanpur',
        'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 'patna',
        'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad',
        'meerut', 'rajkot', 'kalyan', 'vasai', 'varanasi', 'srinagar',
        'aurangabad', 'dhanbad', 'amritsar', 'navi', 'allahabad', 'howrah',
        'ranchi', 'jabalpur', 'gwalior', 'vijayawada', 'jodhpur', 'madurai',
        'raipur', 'kota', 'chandigarh', 'guwahati', 'solapur', 'hubli',
        
        // States (usually context, not keywords)
        'maharashtra', 'uttar pradesh', 'bihar', 'west bengal', 'madhya pradesh',
        'tamil nadu', 'rajasthan', 'karnataka', 'gujarat', 'andhra pradesh',
        'odisha', 'telangana', 'kerala', 'jharkhand', 'assam', 'punjab',
        'chhattisgarh', 'haryana', 'uttarakhand', 'himachal pradesh',
        'tripura', 'meghalaya', 'manipur', 'nagaland', 'goa', 'arunachal pradesh',
        'mizoram', 'sikkim',
        
        // Generic business terms
        'company', 'companies', 'firm', 'firms', 'business', 'businesses',
        'industry', 'industries', 'sector', 'sectors', 'market', 'markets',
        'growth', 'development', 'plan', 'plans', 'planning', 'proposed',
        'proposal', 'proposals', 'initiative', 'initiatives', 'scheme', 'schemes',
        'program', 'programme', 'programs', 'programmes', 'project', 'projects',
        'expected', 'likely', 'set', 'look', 'looks', 'looking', 'move',
        'moves', 'moving', 'step', 'steps', 'way', 'ways', 'part', 'parts',
        'order', 'orders', 'decision', 'decisions', 'made', 'make', 'making',
        'take', 'takes', 'taking', 'taken', 'give', 'gives', 'given', 'giving',
        'get', 'gets', 'got', 'getting', 'put', 'puts', 'putting',
        'come', 'comes', 'came', 'go', 'goes', 'went', 'gone',
        'see', 'sees', 'saw', 'seen', 'know', 'knows', 'knew', 'known',
        'think', 'thinks', 'thought', 'want', 'wants', 'wanted',
        'use', 'uses', 'used', 'using', 'include', 'includes', 'including',
        'included', 'need', 'needs', 'needed', 'work', 'works', 'worked', 'working',
        'help', 'helps', 'helped', 'helping', 'show', 'shows', 'showed', 'shown',
        'try', 'tries', 'tried', 'trying', 'keep', 'keeps', 'kept', 'keeping',
        'let', 'lets', 'leave', 'leaves', 'left', 'begin', 'begins', 'began',
        'seem', 'seems', 'seemed', 'feel', 'feels', 'felt', 'become', 'becomes',
        'became', 'call', 'calls', 'called', 'calling', 'ask', 'asks', 'asked',
        'run', 'runs', 'ran', 'running', 'turn', 'turns', 'turned', 'turning',
        'hold', 'holds', 'held', 'holding', 'bring', 'brings', 'brought',
        'write', 'writes', 'wrote', 'written', 'provide', 'provides', 'provided',
        'continue', 'continues', 'continued', 'follow', 'follows', 'followed',
        'stop', 'stops', 'stopped', 'create', 'creates', 'created', 'creating',
        'speak', 'speaks', 'spoke', 'spoken', 'read', 'reads', 'allow', 'allows',
        'add', 'adds', 'added', 'spend', 'spends', 'spent', 'win', 'wins', 'won',
        'offer', 'offers', 'offered', 'remember', 'considers', 'appear', 'appears',
        'buy', 'buys', 'bought', 'wait', 'waits', 'serve', 'serves', 'die', 'dies',
        'send', 'sends', 'sent', 'expect', 'expects', 'build', 'builds', 'built',
        'stay', 'stays', 'fall', 'falls', 'fell', 'cut', 'cuts', 'reach', 'reaches',
        'kill', 'kills', 'remain', 'remains', 'suggest', 'suggests', 'raise', 'raises',
        'pass', 'passes', 'passed', 'sell', 'sells', 'sold', 'require', 'requires',
        'meet', 'meets', 'met', 'pay', 'pays', 'paid', 'hear', 'hears', 'heard',
        'lose', 'loses', 'lost', 'watch', 'watches', 'carry', 'carries', 'carried',
        'cause', 'causes', 'caused', 'support', 'supports', 'supported',
        'hit', 'hits', 'produce', 'produces', 'change', 'changes', 'changed',
    ]);
    
    // =========================================
    // PERSON NAME PATTERNS
    // =========================================
    const NAME_PATTERNS = [
        /^(mr|mrs|ms|dr|prof|shri|smt|km|justice|hon|adv)\s/i,
        /\b(kumar|singh|sharma|verma|gupta|patel|reddy|rao|nair|iyer|menon|pillai|das|roy|sen|bose|chatterjee|banerjee|mukherjee|ghosh|mishra|pandey|tiwari|dubey|trivedi|yadav|chauhan|rathore|rajput|thakur|joshi|kulkarni|deshmukh|patil|pawar|chavan|jadhav|shinde|gaikwad|kadam|more|kale|sawant|deshpande|jain|agarwal|goel|goyal|mittal|bansal|singhal|mahajan|arora|suri|khanna|malhotra|kapoor|sahni|bhatia|kohli|sethi|sodhi|bajaj|dhawan|mehra|chopra|anand|grover)\b/i,
    ];
    
    // =========================================
    // SYNONYM MAPPING (for deduplication)
    // =========================================
    const SYNONYMS = {
        'rbi': 'reserve bank of india',
        'reserve bank': 'reserve bank of india',
        'sebi': 'securities exchange board',
        'securities board': 'securities exchange board',
        'gst': 'goods and services tax',
        'goods services tax': 'goods and services tax',
        'upi': 'unified payments interface',
        'digital payments': 'unified payments interface',
        'cbdc': 'central bank digital currency',
        'digital rupee': 'central bank digital currency',
        'dpdp': 'data protection',
        'pdpb': 'data protection',
        'personal data protection': 'data protection',
        'digital personal data': 'data protection',
        'npa': 'non performing assets',
        'non-performing asset': 'non performing assets',
        'bad loans': 'non performing assets',
        'fdi': 'foreign direct investment',
        'foreign investment': 'foreign direct investment',
        'ibc': 'insolvency bankruptcy',
        'bankruptcy code': 'insolvency bankruptcy',
        'esg': 'environmental social governance',
        'sustainable investing': 'environmental social governance',
        'ai': 'artificial intelligence',
        'machine learning': 'artificial intelligence',
        'electric vehicles': 'electric vehicle',
        'ev': 'electric vehicle',
        'evs': 'electric vehicle',
        'renewable': 'renewable energy',
        'solar': 'renewable energy',
        'wind power': 'renewable energy',
        'clean energy': 'renewable energy',
        'fintech': 'financial technology',
        'neo bank': 'financial technology',
        'digital bank': 'financial technology',
        'ondc': 'open network digital commerce',
        'startup': 'startups',
        'start-up': 'startups',
        'start up': 'startups',
    };
    
    // =========================================
    // UTILITY FUNCTIONS
    // =========================================
    
    /**
     * Check if a phrase exists as a known multi-word term
     */
    function isKnownPhrase(text) {
        return KNOWN_PHRASES.has(text.toLowerCase().trim());
    }
    
    /**
     * Expand an acronym to its full form
     */
    function expandAcronym(text) {
        const lower = text.toLowerCase().trim();
        return ACRONYMS[lower] || null;
    }
    
    /**
     * Check if a word is a stopword
     */
    function isStopword(word) {
        return STOPWORDS.has(word.toLowerCase().trim());
    }
    
    /**
     * Check if text looks like a person's name
     */
    function isPersonName(text) {
        const lower = text.toLowerCase().trim();
        
        // Check title patterns
        for (const pattern of NAME_PATTERNS) {
            if (pattern.test(lower)) return true;
        }
        
        // Check if it's 2-3 capitalized words (likely a name)
        const words = text.split(/\s+/);
        if (words.length >= 2 && words.length <= 3) {
            const allCapitalized = words.every(w => /^[A-Z]/.test(w));
            const hasCommonSurname = NAME_PATTERNS[1].test(text);
            if (allCapitalized && hasCommonSurname) return true;
        }
        
        return false;
    }
    
    /**
     * Normalize a keyword to its canonical form
     */
    function normalize(text) {
        if (!text) return null;
        
        let normalized = text.toLowerCase().trim();
        
        // Check synonyms
        if (SYNONYMS[normalized]) {
            normalized = SYNONYMS[normalized];
        }
        
        // Expand acronyms to full form for consistency
        const expanded = expandAcronym(normalized);
        if (expanded) {
            normalized = expanded.toLowerCase();
        }
        
        return normalized;
    }
    
    /**
     * Extract keywords from a single text
     */
    function extractFromText(text, options = {}) {
        if (!text) return [];
        
        const {
            minLength = 3,
            maxWords = 4,
            includeAcronyms = true,
            filterNames = true,
        } = options;
        
        const keywords = new Map(); // keyword -> count
        const textLower = text.toLowerCase();
        
        // 1. Extract known phrases first (multi-word)
        for (const phrase of KNOWN_PHRASES) {
            if (textLower.includes(phrase)) {
                const normalized = normalize(phrase) || phrase;
                keywords.set(normalized, (keywords.get(normalized) || 0) + 1);
            }
        }
        
        // 2. Extract acronyms
        if (includeAcronyms) {
            const acronymPattern = /\b[A-Z]{2,6}\b/g;
            let match;
            while ((match = acronymPattern.exec(text)) !== null) {
                const acronym = match[0].toLowerCase();
                if (ACRONYMS[acronym]) {
                    const normalized = normalize(acronym) || acronym;
                    keywords.set(normalized, (keywords.get(normalized) || 0) + 1);
                }
            }
        }
        
        // 3. Extract remaining words
        const words = text
            .toLowerCase()
            .replace(/[^a-z0-9\s-]/g, ' ')
            .split(/\s+/)
            .filter(w => w.length >= minLength && !isStopword(w));
        
        for (const word of words) {
            // Skip if already captured as part of a phrase
            let isPartOfPhrase = false;
            for (const phrase of keywords.keys()) {
                if (phrase.includes(word)) {
                    isPartOfPhrase = true;
                    break;
                }
            }
            
            if (!isPartOfPhrase) {
                const normalized = normalize(word) || word;
                keywords.set(normalized, (keywords.get(normalized) || 0) + 1);
            }
        }
        
        // 4. Filter out person names if enabled
        if (filterNames) {
            for (const [keyword] of keywords) {
                if (isPersonName(keyword)) {
                    keywords.delete(keyword);
                }
            }
        }
        
        return Array.from(keywords.entries())
            .map(([keyword, count]) => ({ keyword, count }))
            .sort((a, b) => b.count - a.count);
    }
    
    /**
     * Extract keywords from multiple articles
     * Returns aggregated keyword frequency across all articles
     */
    function extractFromArticles(articles, options = {}) {
        const {
            fields = ['title', 'summary', 'keywords'],
            minOccurrences = 2,
            topN = 100,
            ...textOptions
        } = options;
        
        const globalKeywords = new Map(); // keyword -> { count, articles: Set }
        
        for (const article of articles) {
            const articleKeywords = new Set();
            
            for (const field of fields) {
                if (article[field]) {
                    let text = article[field];
                    if (Array.isArray(text)) {
                        text = text.join(' ');
                    }
                    
                    const extracted = extractFromText(text, textOptions);
                    for (const { keyword } of extracted) {
                        articleKeywords.add(keyword);
                    }
                }
            }
            
            // Add to global counts
            for (const keyword of articleKeywords) {
                if (!globalKeywords.has(keyword)) {
                    globalKeywords.set(keyword, { count: 0, articles: new Set() });
                }
                const entry = globalKeywords.get(keyword);
                entry.count++;
                entry.articles.add(article.url || article.id);
            }
        }
        
        // Filter and sort
        return Array.from(globalKeywords.entries())
            .filter(([_, data]) => data.count >= minOccurrences)
            .map(([keyword, data]) => ({
                keyword,
                count: data.count,
                articles: Array.from(data.articles),
            }))
            .sort((a, b) => b.count - a.count)
            .slice(0, topN);
    }
    
    /**
     * Group keywords into semantic categories
     */
    function groupKeywords(keywords) {
        const CATEGORIES = {
            'Economy & Finance': /\b(gdp|inflation|fiscal|monetary|budget|tax|revenue|deficit|debt|bond|yield|market|stock|investment|banking|loan|credit|interest|rupee|forex)\b/i,
            'Regulation & Policy': /\b(regulation|policy|bill|act|law|compliance|guideline|directive|notification|circular|amendment|reform)\b/i,
            'Banking & Finance': /\b(rbi|bank|nbfc|lending|deposit|npa|asset|liability|liquidity|reserve|payment|settlement)\b/i,
            'Digital & Technology': /\b(digital|technology|fintech|ai|data|cyber|cloud|platform|app|software|internet|online)\b/i,
            'Trade & Commerce': /\b(trade|export|import|commerce|customs|tariff|duty|wto|fta|manufacturing)\b/i,
            'Infrastructure': /\b(infrastructure|highway|rail|port|airport|power|energy|construction|development)\b/i,
            'Healthcare': /\b(health|medical|pharma|drug|hospital|insurance|ayushman)\b/i,
            'Agriculture': /\b(agriculture|farm|crop|food|msp|apmc|kisan|rural)\b/i,
            'Environment': /\b(environment|climate|carbon|emission|renewable|solar|green|sustainable)\b/i,
        };
        
        const groups = {};
        const ungrouped = [];
        
        for (const item of keywords) {
            let placed = false;
            for (const [category, pattern] of Object.entries(CATEGORIES)) {
                if (pattern.test(item.keyword)) {
                    if (!groups[category]) groups[category] = [];
                    groups[category].push(item);
                    placed = true;
                    break;
                }
            }
            if (!placed) {
                ungrouped.push(item);
            }
        }
        
        if (ungrouped.length > 0) {
            groups['Other'] = ungrouped;
        }
        
        return groups;
    }
    
    // =========================================
    // PUBLIC API
    // =========================================
    return {
        // Core functions
        extractFromText,
        extractFromArticles,
        normalize,
        groupKeywords,
        
        // Utility functions
        isKnownPhrase,
        expandAcronym,
        isStopword,
        isPersonName,
        
        // Constants (for external use if needed)
        KNOWN_PHRASES: Object.freeze(KNOWN_PHRASES),
        ACRONYMS: Object.freeze(ACRONYMS),
        STOPWORDS: Object.freeze(STOPWORDS),
        SYNONYMS: Object.freeze(SYNONYMS),
        
        // Version
        VERSION: '6.2.0',
    };
})();

// Export for Node.js environments
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PolicyKeywords;
}
