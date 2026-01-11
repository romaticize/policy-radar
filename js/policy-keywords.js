/**
 * PolicyRadar - Unified Policy Keywords Module
 * =============================================
 * 
 * This module provides consistent keyword extraction across:
 * - Topic Explorer
 * - Knowledge Graph
 * - Search functionality
 * 
 * Features:
 * - Multi-word policy phrase detection
 * - Known acronym handling
 * - Indian English stopword filtering
 * - Person name filtering
 * - Synonym normalization
 * 
 * Usage:
 *   <script src="js/policy-keywords.js"></script>
 *   <script>
 *     const keywords = PolicyKeywords.extract("RBI announces new digital lending guidelines...");
 *     // Returns: ['RBI', 'digital lending', 'guidelines', ...]
 *   </script>
 */

const PolicyKeywords = (function() {
    'use strict';
    
    // ========================================
    // KNOWN POLICY PHRASES (Multi-word terms)
    // ========================================
    const POLICY_PHRASES = new Set([
        // Programs & Initiatives
        'digital india', 'make in india', 'startup india', 'skill india',
        'swachh bharat', 'ayushman bharat', 'atmanirbhar bharat', 'jan dhan',
        'pm kisan', 'pm awas', 'pm garib kalyan', 'pm vishwakarma',
        'production linked incentive', 'pli scheme', 'national monetization pipeline',
        'smart cities', 'bullet train', 'dedicated freight corridor',
        'bharatmala', 'sagarmala', 'gati shakti',
        
        // Legal/Regulatory
        'data protection', 'digital personal data', 'dpdp act', 'it act',
        'companies act', 'insolvency bankruptcy', 'ibc', 'gst council',
        'goods services tax', 'income tax', 'direct tax', 'indirect tax',
        'labour codes', 'labour laws', 'minimum wage', 'social security',
        'competition act', 'cci', 'consumer protection', 'ccpa',
        'environmental clearance', 'eia', 'forest clearance',
        
        // Financial/Economic
        'monetary policy', 'fiscal policy', 'union budget', 'finance bill',
        'credit policy', 'repo rate', 'reverse repo', 'crr', 'slr',
        'foreign exchange', 'fdi policy', 'fdi limit', 'fii',
        'capital gains', 'tds', 'tcs', 'advance tax',
        'current account deficit', 'trade deficit', 'fiscal deficit',
        'debt market', 'bond market', 'equity market',
        'sovereign bond', 'green bond', 'infrastructure bond',
        
        // Sectors
        'renewable energy', 'solar power', 'wind energy', 'green hydrogen',
        'electric vehicle', 'ev policy', 'battery storage', 'charging infrastructure',
        'semiconductor', 'chip manufacturing', 'electronics manufacturing',
        'pharmaceutical', 'drug pricing', 'clinical trial', 'nlem',
        'telecom', 'spectrum auction', 'right of way', '5g rollout',
        'real estate', 'rera', 'affordable housing', 'housing for all',
        
        // Institutions
        'supreme court', 'high court', 'nclat', 'nclt', 'sat', 'drt',
        'reserve bank', 'central bank', 'finance ministry', 'pmo',
        'niti aayog', 'planning commission', 'cabinet committee',
        'lok sabha', 'rajya sabha', 'parliament session', 'joint sitting',
        'election commission', 'delimitation commission',
        'cag', 'comptroller auditor', 'statutory auditor',
        
        // Governance
        'public procurement', 'government tender', 'gem portal',
        'ease of doing', 'single window', 'one nation one',
        'disinvestment', 'strategic disinvestment', 'privatization',
        'public sector', 'maharatna', 'navratna', 'miniratna',
        'special economic zone', 'sez', 'industrial corridor', 'nimz',
        
        // International
        'free trade', 'fta', 'rcep', 'wto', 'bilateral treaty',
        'foreign policy', 'diplomatic relations', 'g20', 'brics', 'quad',
        'mou signed', 'bilateral agreement', 'trade agreement',
        
        // Technology/Digital
        'artificial intelligence', 'machine learning', 'deep tech',
        'upi', 'digital payment', 'payment gateway', 'payment aggregator',
        'digital rupee', 'cbdc', 'central bank digital',
        'open network', 'ondc', 'account aggregator', 'aa framework',
        'aadhaar', 'digilocker', 'e-kyc', 'video kyc',
    ]);
    
    // ========================================
    // KNOWN ACRONYMS
    // ========================================
    const KNOWN_ACRONYMS = new Set([
        // Regulators
        'RBI', 'SEBI', 'IRDAI', 'PFRDA', 'IBBI', 'NHB', 'NABARD', 'SIDBI', 'EXIM',
        'CCI', 'TRAI', 'CERC', 'AERC', 'DGFT', 'CBIC', 'CBDT', 'FSSAI', 'BIS',
        'NPCI', 'CCPA', 'NCLT', 'NCLAT', 'SAT', 'DRT', 'DRAT',
        
        // Government Bodies
        'PMO', 'MoF', 'MEA', 'MHA', 'MoD', 'MoCI', 'DPIIT', 'MEITY', 'DoT',
        'MoRTH', 'MoHUA', 'MoSPI', 'MoEFCC', 'MoHFW', 'MoE', 'MoST',
        'CAG', 'CVC', 'CBI', 'ED', 'NIA', 'NCB',
        
        // Economic/Financial
        'GDP', 'GNP', 'CPI', 'WPI', 'IIP', 'PMI', 'GST', 'TDS', 'TCS',
        'FDI', 'FII', 'FPI', 'ECB', 'FEMA', 'FCRA', 'NPA', 'ARC',
        'CRR', 'SLR', 'MSF', 'LAF', 'OMO', 'LTRO', 'TLTRO',
        'NBFC', 'HFC', 'ARCs', 'DFI', 'IFC', 'NaBFID',
        'IPO', 'OFS', 'FPO', 'QIP', 'NCD', 'CP', 'CD',
        
        // Technology/Digital
        'UPI', 'IMPS', 'NEFT', 'RTGS', 'NACH', 'AEPS', 'BBPS',
        'CBDC', 'ONDC', 'DigiLocker', 'UIDAI', 'NPCI',
        'API', 'SDK', 'SaaS', 'PaaS', 'IaaS', 'GenAI',
        
        // Programs/Schemes
        'PLI', 'MSME', 'PSU', 'PSE', 'PSB', 'SEZ', 'EOU', 'STPI',
        'NMP', 'NIP', 'NHM', 'NREGA', 'MGNREGA', 'PMAY', 'PMJAY', 'PMJDY',
        'NEET', 'JEE', 'CUET', 'UGC', 'AICTE', 'NAAC', 'NBA',
        
        // Legal
        'IPC', 'CrPC', 'CPC', 'BNS', 'BNSS', 'BSA',
        'DPDP', 'PDPB', 'ITA', 'PMLA', 'POCA', 'RTI', 'PIL',
        
        // International
        'WTO', 'IMF', 'WB', 'ADB', 'AIIB', 'NDB', 'BRICS', 'SCO', 'ASEAN',
        'FTA', 'CEPA', 'CECA', 'DTAA', 'MFN', 'TRQ',
        'G7', 'G20', 'QUAD', 'IPEF', 'I2U2',
        
        // Industry
        'EV', 'ICE', 'BEV', 'PHEV', 'HEV', 'CNG', 'LNG', 'LPG', 'PNG',
        'RE', 'ESG', 'CSR', 'SDG', 'GHG', 'NDC', 'COP',
    ]);
    
    // ========================================
    // STOPWORDS (Indian English Extended)
    // ========================================
    const STOPWORDS = new Set([
        // Standard English
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'what', 'which', 'who', 'whom',
        'whose', 'where', 'when', 'why', 'how', 'all', 'each', 'every',
        'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not',
        'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also',
        'now', 'here', 'there', 'then', 'once', 'its', 'it', 'he', 'she',
        'him', 'her', 'his', 'they', 'them', 'their', 'we', 'us', 'our',
        'i', 'me', 'my', 'you', 'your', 'up', 'down', 'out', 'off', 'over',
        'under', 'again', 'further', 'being', 'having', 'doing', 'about',
        'against', 'between', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'any', 'even', 'because', 'while', 'if', 'until',
        
        // Indian English - Numbers/Currency
        'crore', 'crores', 'lakh', 'lakhs', 'rupee', 'rupees', 'rs', 'inr',
        'billion', 'million', 'thousand', 'percent', 'percentage', 'per',
        
        // Indian English - Common Words
        'said', 'says', 'according', 'stated', 'told', 'reported', 'added',
        'noted', 'announced', 'expected', 'likely', 'may', 'would', 'could',
        'year', 'years', 'month', 'months', 'week', 'weeks', 'day', 'days',
        'today', 'yesterday', 'tomorrow', 'monday', 'tuesday', 'wednesday',
        'thursday', 'friday', 'saturday', 'sunday', 'january', 'february',
        'march', 'april', 'june', 'july', 'august', 'september', 'october',
        'november', 'december', 'fy', 'q1', 'q2', 'q3', 'q4', 'h1', 'h2',
        
        // Common verbs
        'get', 'got', 'give', 'gave', 'take', 'took', 'make', 'made',
        'come', 'came', 'go', 'went', 'see', 'saw', 'know', 'knew',
        'think', 'thought', 'find', 'found', 'want', 'wanted', 'use', 'used',
        
        // Common nouns (too generic)
        'thing', 'things', 'time', 'times', 'way', 'ways', 'case', 'cases',
        'point', 'points', 'part', 'parts', 'place', 'places', 'people',
        'man', 'men', 'woman', 'women', 'child', 'children', 'world',
        'government', 'country', 'state', 'city', 'area', 'level', 'number',
        'issue', 'issues', 'matter', 'matters', 'order', 'orders',
        
        // Major Indian Cities (too common)
        'delhi', 'mumbai', 'bangalore', 'bengaluru', 'chennai', 'kolkata',
        'hyderabad', 'ahmedabad', 'pune', 'jaipur', 'lucknow', 'kanpur',
        'nagpur', 'indore', 'bhopal', 'patna', 'vadodara', 'ghaziabad',
        'ludhiana', 'agra', 'nashik', 'surat', 'rajkot', 'noida', 'gurgaon',
        'gurugram', 'faridabad', 'chandigarh', 'coimbatore', 'kochi',
        'thiruvananthapuram', 'visakhapatnam', 'vijayawada', 'mysore',
        
        // States (too common without context)
        'maharashtra', 'karnataka', 'tamil', 'nadu', 'andhra', 'pradesh',
        'telangana', 'kerala', 'gujarat', 'rajasthan', 'madhya', 'uttar',
        'bihar', 'west', 'bengal', 'odisha', 'jharkhand', 'chhattisgarh',
        'assam', 'punjab', 'haryana', 'uttarakhand', 'himachal', 'jammu',
        'kashmir', 'goa', 'tripura', 'meghalaya', 'manipur', 'mizoram',
        'arunachal', 'nagaland', 'sikkim',
        
        // News-speak
        'new', 'latest', 'breaking', 'update', 'updates', 'news', 'report',
        'reports', 'article', 'story', 'read', 'click', 'here', 'more',
        'view', 'details', 'full', 'complete', 'official', 'source',
        'live', 'exclusive', 'special', 'top', 'best', 'first', 'last',
    ]);
    
    // ========================================
    // PERSON NAME PATTERNS
    // ========================================
    const PERSON_PREFIXES = ['mr', 'mrs', 'ms', 'dr', 'prof', 'shri', 'smt', 'km', 'sri'];
    const PERSON_SUFFIXES = ['ji', 'sahab', 'saheb', 'babu', 'sir', 'madam'];
    
    // Common Indian first names and last names (sample)
    const COMMON_NAMES = new Set([
        'kumar', 'singh', 'sharma', 'verma', 'gupta', 'jain', 'agarwal',
        'patel', 'shah', 'mehta', 'desai', 'joshi', 'kulkarni', 'patil',
        'iyer', 'nair', 'menon', 'pillai', 'rao', 'reddy', 'naidu',
        'modi', 'gandhi', 'nehru', 'jaitley', 'sitharaman', 'goyal',
        'rajnath', 'gadkari', 'javadekar', 'prasad', 'shah', 'tomar',
        'amit', 'rahul', 'narendra', 'nirmala', 'piyush', 'rajiv',
        'sonia', 'priyanka', 'smriti', 'ntin', 'yogi', 'mamata',
        'arvind', 'kejriwal', 'uddhav', 'thackeray', 'sharad', 'pawar',
    ]);
    
    // ========================================
    // SYNONYM MAPPING
    // ========================================
    const SYNONYMS = {
        'reserve bank': 'RBI',
        'reserve bank of india': 'RBI',
        'central bank': 'RBI',
        'securities exchange board': 'SEBI',
        'securities and exchange board': 'SEBI',
        'income tax department': 'CBDT',
        'customs': 'CBIC',
        'goods and services tax': 'GST',
        'prime minister': 'PM',
        "prime minister's office": 'PMO',
        'finance minister': 'FM',
        'finance ministry': 'MoF',
        'ministry of finance': 'MoF',
        'foreign direct investment': 'FDI',
        'united progressive alliance': 'UPA',
        'national democratic alliance': 'NDA',
        'bharatiya janata party': 'BJP',
        'indian national congress': 'INC',
        'aam aadmi party': 'AAP',
        'communist party': 'CPM',
        'trinamool congress': 'TMC',
        'production linked incentive': 'PLI',
        'digital personal data protection': 'DPDP',
        'central bank digital currency': 'CBDC',
        'open network for digital commerce': 'ONDC',
        'unified payments interface': 'UPI',
        'non performing asset': 'NPA',
        'non-performing asset': 'NPA',
        'public sector undertaking': 'PSU',
        'public sector bank': 'PSB',
        'special economic zone': 'SEZ',
        'micro small medium enterprise': 'MSME',
        'small and medium enterprise': 'SME',
        'electric vehicle': 'EV',
        'environmental social governance': 'ESG',
        'corporate social responsibility': 'CSR',
        'artificial intelligence': 'AI',
        'machine learning': 'ML',
    };
    
    // ========================================
    // EXTRACTION FUNCTIONS
    // ========================================
    
    /**
     * Check if a word looks like a person's name
     */
    function isPersonName(word) {
        const lower = word.toLowerCase();
        
        // Check common names
        if (COMMON_NAMES.has(lower)) return true;
        
        // Check prefixes/suffixes
        for (const prefix of PERSON_PREFIXES) {
            if (lower.startsWith(prefix + ' ') || lower.startsWith(prefix + '.')) {
                return true;
            }
        }
        
        // Capitalized word not in known lists (heuristic)
        if (word.length > 2 && 
            word[0] === word[0].toUpperCase() && 
            word.slice(1) === word.slice(1).toLowerCase() &&
            !KNOWN_ACRONYMS.has(word.toUpperCase())) {
            // Could be a name - check if it looks like a proper noun
            return COMMON_NAMES.has(lower);
        }
        
        return false;
    }
    
    /**
     * Normalize a keyword using synonyms
     */
    function normalize(keyword) {
        const lower = keyword.toLowerCase().trim();
        return SYNONYMS[lower] || keyword;
    }
    
    /**
     * Extract keywords from text
     * @param {string} text - Input text
     * @param {Object} options - Extraction options
     * @returns {string[]} - Array of extracted keywords
     */
    function extract(text, options = {}) {
        if (!text || typeof text !== 'string') return [];
        
        const {
            maxKeywords = 20,
            minLength = 2,
            includeAcronyms = true,
            includePhrases = true,
            normalizeOutput = true,
            filterNames = true,
        } = options;
        
        const keywords = new Map(); // keyword -> count
        const textLower = text.toLowerCase();
        
        // 1. Extract known multi-word phrases
        if (includePhrases) {
            for (const phrase of POLICY_PHRASES) {
                if (textLower.includes(phrase)) {
                    const normalized = normalizeOutput ? normalize(phrase) : phrase;
                    keywords.set(normalized, (keywords.get(normalized) || 0) + 2); // Boost phrases
                }
            }
        }
        
        // 2. Extract known acronyms
        if (includeAcronyms) {
            for (const acronym of KNOWN_ACRONYMS) {
                // Match as whole word with word boundaries
                const regex = new RegExp(`\\b${acronym}\\b`, 'g');
                const matches = text.match(regex);
                if (matches) {
                    keywords.set(acronym, (keywords.get(acronym) || 0) + matches.length * 2);
                }
            }
        }
        
        // 3. Extract remaining words
        const words = text
            .replace(/[^\w\s'-]/g, ' ')
            .split(/\s+/)
            .filter(w => w.length >= minLength);
        
        for (const word of words) {
            const lower = word.toLowerCase();
            
            // Skip stopwords
            if (STOPWORDS.has(lower)) continue;
            
            // Skip numbers
            if (/^\d+$/.test(word)) continue;
            
            // Skip very short words
            if (word.length < minLength) continue;
            
            // Skip person names if filtering enabled
            if (filterNames && isPersonName(word)) continue;
            
            // Skip if it's part of an already-extracted phrase
            let isPartOfPhrase = false;
            for (const phrase of keywords.keys()) {
                if (phrase.toLowerCase().includes(lower) && phrase.includes(' ')) {
                    isPartOfPhrase = true;
                    break;
                }
            }
            if (isPartOfPhrase) continue;
            
            // Add keyword
            const normalized = normalizeOutput ? normalize(word) : word;
            keywords.set(normalized, (keywords.get(normalized) || 0) + 1);
        }
        
        // 4. Sort by count and return top keywords
        return Array.from(keywords.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, maxKeywords)
            .map(([keyword]) => keyword);
    }
    
    /**
     * Check if a word is a known policy term
     */
    function isKnownTerm(word) {
        const lower = word.toLowerCase();
        return POLICY_PHRASES.has(lower) || 
               KNOWN_ACRONYMS.has(word.toUpperCase()) ||
               Object.keys(SYNONYMS).includes(lower);
    }
    
    /**
     * Get related terms for a keyword
     */
    function getRelated(keyword) {
        const lower = keyword.toLowerCase();
        const related = [];
        
        // Find synonyms
        for (const [phrase, acronym] of Object.entries(SYNONYMS)) {
            if (phrase.includes(lower) || acronym.toLowerCase() === lower) {
                related.push(phrase, acronym);
            }
        }
        
        // Find phrases containing this word
        for (const phrase of POLICY_PHRASES) {
            if (phrase.includes(lower) && phrase !== lower) {
                related.push(phrase);
            }
        }
        
        return [...new Set(related)];
    }
    
    // ========================================
    // PUBLIC API
    // ========================================
    return {
        extract,
        normalize,
        isKnownTerm,
        getRelated,
        isPersonName,
        
        // Expose datasets for extension
        POLICY_PHRASES,
        KNOWN_ACRONYMS,
        STOPWORDS,
        SYNONYMS,
    };
})();

// Export for Node.js if applicable
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PolicyKeywords;
}
