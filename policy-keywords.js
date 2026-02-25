/**
 * PolicyRadar - Unified Policy Keywords Module
 * =============================================
 * Centralized keyword extraction, normalization, and categorization
 * for Topic Explorer and Knowledge Graph visualizations.
 * 
 * Features:
 * - Multi-word phrase detection (e.g., "Digital India", "Make in India")
 * - Acronym expansion and normalization
 * - Indian English stopwords filtering
 * - Person name detection and filtering
 * - Synonym mapping for deduplication
 * - Category-based keyword grouping
 */

const PolicyKeywords = (function() {
    'use strict';

    // ============================================
    // KNOWN POLICY PHRASES (Multi-word)
    // ============================================
    const POLICY_PHRASES = [
        // Major Initiatives
        'Digital India', 'Make in India', 'Startup India', 'Skill India',
        'Atmanirbhar Bharat', 'Swachh Bharat', 'Ayushman Bharat', 'Jan Dhan',
        'PM Kisan', 'PM Awas', 'PM Ujjwala', 'PM Mudra', 'PM Vishwakarma',
        'National Education Policy', 'New Education Policy', 'NEP 2020',
        'Production Linked Incentive', 'PLI Scheme', 'Smart Cities',
        'Sagarmala', 'Bharatmala', 'Gati Shakti', 'National Infrastructure Pipeline',
        
        // Digital Public Infrastructure
        'Unified Payments Interface', 'UPI', 'Aadhaar', 'DigiLocker',
        'ONDC', 'Open Network for Digital Commerce', 'Digital Public Infrastructure',
        'India Stack', 'Account Aggregator', 'CBDC', 'Digital Rupee',
        'e-RUPI', 'CoWIN', 'Ayushman Bharat Digital Mission', 'ABDM',
        
        // Financial Regulation
        'Reserve Bank of India', 'RBI', 'SEBI', 'IRDAI', 'PFRDA', 'IBBI',
        'Insolvency and Bankruptcy', 'IBC', 'NCLT', 'NCLAT',
        'Foreign Direct Investment', 'FDI', 'Foreign Portfolio Investment', 'FPI',
        'Monetary Policy Committee', 'MPC', 'Repo Rate', 'CRR', 'SLR',
        'Non-Performing Asset', 'NPA', 'Asset Reconstruction', 'ARC',
        'Payment Aggregator', 'Payment Gateway', 'NBFC', 'HFC',
        
        // Taxation
        'Goods and Services Tax', 'GST', 'GST Council', 'IGST', 'CGST', 'SGST',
        'Income Tax', 'Direct Tax', 'Indirect Tax', 'TDS', 'TCS',
        'Advance Pricing Agreement', 'APA', 'Transfer Pricing',
        'Faceless Assessment', 'Vivad se Vishwas',
        
        // Labour & Employment
        'Labour Code', 'Labour Law', 'Industrial Relations Code',
        'Code on Wages', 'Code on Social Security', 'Occupational Safety Code',
        'EPFO', 'Employees Provident Fund', 'ESIC', 'Employees State Insurance',
        'Minimum Wage', 'Living Wage', 'Gig Worker', 'Platform Worker',
        'Fixed Term Employment', 'Contract Labour',
        
        // Data & Privacy
        'Digital Personal Data Protection', 'DPDP Act', 'DPDPA',
        'Data Protection', 'Data Privacy', 'Data Localization',
        'IT Act', 'Information Technology Act', 'IT Rules',
        'Intermediary Guidelines', 'Safe Harbour',
        
        // Trade & Commerce
        'Foreign Trade Policy', 'FTP', 'Export Promotion',
        'Special Economic Zone', 'SEZ', 'Export Oriented Unit', 'EOU',
        'DGFT', 'Director General of Foreign Trade',
        'Anti-Dumping', 'Countervailing Duty', 'Safeguard Duty',
        'Free Trade Agreement', 'FTA', 'Comprehensive Economic Partnership',
        'Regional Comprehensive Economic Partnership', 'RCEP',
        
        // Energy & Environment
        'National Green Tribunal', 'NGT', 'Environment Clearance',
        'Environmental Impact Assessment', 'EIA', 'Coastal Regulation Zone', 'CRZ',
        'Renewable Energy', 'Solar Energy', 'Wind Energy', 'Green Hydrogen',
        'National Solar Mission', 'Green Energy Corridor',
        'Carbon Credit', 'Carbon Market', 'Net Zero', 'Energy Transition',
        'Electric Vehicle', 'EV Policy', 'FAME Scheme',
        
        // Infrastructure
        'National Highways Authority', 'NHAI', 'Toll Road', 'BOT', 'HAM',
        'Dedicated Freight Corridor', 'DFC', 'High Speed Rail', 'Bullet Train',
        'Metro Rail', 'RRTS', 'Regional Rapid Transit',
        'Airports Authority of India', 'AAI', 'UDAN',
        'Port', 'Sagarmala', 'Inland Waterway',
        
        // Telecom & Tech
        'Telecom Regulatory Authority', 'TRAI', 'Spectrum Auction',
        '5G', '6G', 'Broadband', 'BharatNet', 'Digital Village',
        'National Broadband Mission', 'OTT Regulation',
        'Semiconductor', 'Semicon India', 'Electronics Manufacturing',
        'IT Hardware', 'Data Centre',
        
        // Defence & Security
        'Defence Acquisition', 'DPP', 'DAP', 'Make in India Defence',
        'Strategic Partnership', 'Defence Offset', 'DRDO',
        'Ordnance Factory', 'Defence Corridor', 'Defence Export',
        
        // Agriculture
        'Minimum Support Price', 'MSP', 'Agricultural Produce Marketing',
        'APMC', 'e-NAM', 'National Agriculture Market',
        'Farmer Producer Organization', 'FPO', 'Contract Farming',
        'PM-KISAN', 'Kisan Credit Card', 'KCC', 'Crop Insurance', 'PMFBY',
        
        // Healthcare
        'National Health Mission', 'NHM', 'NRHM', 'NUHM',
        'Pradhan Mantri Jan Arogya Yojana', 'PMJAY', 'Health Insurance',
        'Medical Device', 'Pharmaceutical', 'Drug Price Control', 'NPPA',
        'Clinical Trial', 'Medical Education', 'NEET', 'NMC',
        
        // Education
        'University Grants Commission', 'UGC', 'AICTE', 'NAAC', 'NIRF',
        'Central University', 'IIT', 'IIM', 'NIT', 'IIIT',
        'Skill Development', 'NSDC', 'ITI', 'Apprenticeship',
        
        // Constitutional & Governance
        'Article 370', 'Article 356', 'Article 35A',
        'Tenth Schedule', 'Anti-Defection',
        'Governor', 'President Rule', 'Constitutional Amendment',
        'Lok Sabha', 'Rajya Sabha', 'Parliament Session',
        'Standing Committee', 'Parliamentary Committee', 'Joint Committee',
        'Election Commission', 'Delimitation', 'EVM', 'VVPAT',
        
        // States & UTs
        'Union Territory', 'UT', 'State Legislature', 'Vidhan Sabha',
        'State Budget', 'Finance Commission', 'GST Compensation',
        'Centrally Sponsored Scheme', 'CSS', 'Central Sector Scheme',
    ];

    // ============================================
    // KNOWN ACRONYMS & EXPANSIONS
    // ============================================
    const ACRONYMS = {
        // Regulators
        'RBI': 'Reserve Bank of India',
        'SEBI': 'Securities and Exchange Board of India',
        'IRDAI': 'Insurance Regulatory and Development Authority of India',
        'PFRDA': 'Pension Fund Regulatory and Development Authority',
        'TRAI': 'Telecom Regulatory Authority of India',
        'CCI': 'Competition Commission of India',
        'NCLT': 'National Company Law Tribunal',
        'NCLAT': 'National Company Law Appellate Tribunal',
        'NGT': 'National Green Tribunal',
        'CERC': 'Central Electricity Regulatory Commission',
        'FSSAI': 'Food Safety and Standards Authority of India',
        'BIS': 'Bureau of Indian Standards',
        'NPPA': 'National Pharmaceutical Pricing Authority',
        
        // Government Bodies
        'NITI': 'NITI Aayog',
        'PMO': 'Prime Minister\'s Office',
        'MoF': 'Ministry of Finance',
        'MeitY': 'Ministry of Electronics and IT',
        'DPIIT': 'Department for Promotion of Industry and Internal Trade',
        'DGFT': 'Director General of Foreign Trade',
        'CBDT': 'Central Board of Direct Taxes',
        'CBIC': 'Central Board of Indirect Taxes and Customs',
        'CAG': 'Comptroller and Auditor General',
        
        // Schemes & Initiatives
        'PLI': 'Production Linked Incentive',
        'PMAY': 'Pradhan Mantri Awas Yojana',
        'PMJAY': 'Pradhan Mantri Jan Arogya Yojana',
        'PMKSY': 'Pradhan Mantri Krishi Sinchayee Yojana',
        'PMFBY': 'Pradhan Mantri Fasal Bima Yojana',
        'MGNREGA': 'Mahatma Gandhi National Rural Employment Guarantee Act',
        'UDAN': 'Ude Desh ka Aam Nagrik',
        'FAME': 'Faster Adoption and Manufacturing of Electric Vehicles',
        
        // Financial
        'NPA': 'Non-Performing Asset',
        'ARC': 'Asset Reconstruction Company',
        'NBFC': 'Non-Banking Financial Company',
        'HFC': 'Housing Finance Company',
        'FDI': 'Foreign Direct Investment',
        'FPI': 'Foreign Portfolio Investment',
        'FII': 'Foreign Institutional Investor',
        'PE': 'Private Equity',
        'VC': 'Venture Capital',
        'IPO': 'Initial Public Offering',
        'QIP': 'Qualified Institutional Placement',
        'AIF': 'Alternative Investment Fund',
        'REIT': 'Real Estate Investment Trust',
        'InvIT': 'Infrastructure Investment Trust',
        
        // Tax
        'GST': 'Goods and Services Tax',
        'IGST': 'Integrated GST',
        'CGST': 'Central GST',
        'SGST': 'State GST',
        'TDS': 'Tax Deducted at Source',
        'TCS': 'Tax Collected at Source',
        'MAT': 'Minimum Alternate Tax',
        
        // Digital
        'UPI': 'Unified Payments Interface',
        'NPCI': 'National Payments Corporation of India',
        'ONDC': 'Open Network for Digital Commerce',
        'CBDC': 'Central Bank Digital Currency',
        'ABDM': 'Ayushman Bharat Digital Mission',
        'DPDP': 'Digital Personal Data Protection',
        
        // Infrastructure
        'NHAI': 'National Highways Authority of India',
        'AAI': 'Airports Authority of India',
        'CONCOR': 'Container Corporation of India',
        'DFC': 'Dedicated Freight Corridor',
        'RRTS': 'Regional Rapid Transit System',
        'BOT': 'Build-Operate-Transfer',
        'HAM': 'Hybrid Annuity Model',
        'PPP': 'Public-Private Partnership',
        'EPC': 'Engineering Procurement Construction',
        
        // Energy
        'NTPC': 'National Thermal Power Corporation',
        'NHPC': 'National Hydroelectric Power Corporation',
        'ONGC': 'Oil and Natural Gas Corporation',
        'GAIL': 'Gas Authority of India Limited',
        'IOCL': 'Indian Oil Corporation Limited',
        'BPCL': 'Bharat Petroleum Corporation Limited',
        'HPCL': 'Hindustan Petroleum Corporation Limited',
        
        // Others
        'SEZ': 'Special Economic Zone',
        'EOU': 'Export Oriented Unit',
        'MSME': 'Micro, Small and Medium Enterprises',
        'PSU': 'Public Sector Undertaking',
        'PSE': 'Public Sector Enterprise',
        'CPSEs': 'Central Public Sector Enterprises',
    };

    // ============================================
    // ENHANCED STOPWORDS (Indian English)
    // ============================================
    const STOPWORDS = new Set([
        // Standard English
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
        'he', 'she', 'him', 'her', 'his', 'hers', 'we', 'us', 'our', 'ours',
        'you', 'your', 'yours', 'i', 'me', 'my', 'mine', 'who', 'whom', 'whose',
        'which', 'what', 'where', 'when', 'why', 'how', 'all', 'each', 'every',
        'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
        'also', 'now', 'here', 'there', 'then', 'once', 'if', 'unless', 'until',
        'while', 'during', 'before', 'after', 'above', 'below', 'between',
        'through', 'about', 'against', 'into', 'over', 'under', 'again',
        'further', 'then', 'once', 'any', 'up', 'down', 'out', 'off', 'over',
        
        // Indian English additions
        'crore', 'crores', 'lakh', 'lakhs', 'rupee', 'rupees', 'rs', 'inr',
        'said', 'says', 'told', 'added', 'stated', 'noted', 'mentioned',
        'according', 'per', 'cent', 'percent', 'percentage',
        'year', 'years', 'month', 'months', 'week', 'weeks', 'day', 'days',
        'time', 'times', 'today', 'yesterday', 'tomorrow',
        'first', 'second', 'third', 'last', 'next', 'new', 'old',
        'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
        'hundred', 'thousand', 'million', 'billion', 'trillion',
        'mr', 'mrs', 'ms', 'dr', 'shri', 'smt', 'kumar', 'sharma', 'singh',
        'minister', 'ministry', 'government', 'govt', 'official', 'officials',
        'india', 'indian', 'country', 'nation', 'national', 'state', 'states',
        'report', 'reports', 'news', 'update', 'updates', 'latest',
        'source', 'sources', 'read', 'more', 'click', 'here', 'view',
        
        // Generic news/business words (not policy-specific)
        'high', 'low', 'big', 'small', 'large', 'major', 'minor', 'key', 'top',
        'set', 'get', 'put', 'take', 'make', 'give', 'come', 'go', 'see', 'look',
        'amid', 'amid', 'among', 'despite', 'towards', 'across', 'along',
        'global', 'world', 'international', 'domestic', 'local', 'regional',
        'market', 'markets', 'stock', 'stocks', 'share', 'shares', 'price', 'prices',
        'growth', 'rise', 'fall', 'drop', 'surge', 'jump', 'gain', 'loss',
        'case', 'cases', 'matter', 'issue', 'issues', 'problem', 'problems',
        'court', 'courts', 'judge', 'judges', 'hearing', 'trial', 'verdict',
        'port', 'ports', 'trade', 'trades', 'trading', 'trader', 'traders',
        'tech', 'technology', 'digital', 'online', 'internet', 'web', 'cyber',
        'budget', 'budgets', 'fiscal', 'financial', 'finance', 'economic', 'economy',
        'company', 'companies', 'firm', 'firms', 'business', 'businesses',
        'sector', 'sectors', 'industry', 'industries', 'segment', 'segments',
        'plan', 'plans', 'scheme', 'schemes', 'project', 'projects', 'program',
        'move', 'moves', 'step', 'steps', 'action', 'actions', 'measure', 'measures',
        'deal', 'deals', 'agreement', 'agreements', 'contract', 'contracts',
        'bank', 'banks', 'banking', 'loan', 'loans', 'credit', 'debt',
        'investment', 'investments', 'investor', 'investors', 'fund', 'funds',
        'policy', 'policies', 'rule', 'rules', 'regulation', 'regulations',
        'law', 'laws', 'legal', 'act', 'acts', 'bill', 'bills', 'amendment',
        
        // Political/person names (not policy)
        'trump', 'biden', 'modi', 'shah', 'rahul', 'gandhi', 'kejriwal', 'yogi',
        'bjp', 'congress', 'aap', 'tmc', 'ncp', 'shiv', 'sena', 'jdu', 'rjd',
        'grok', 'openai', 'chatgpt', 'gemini', 'claude', 'bard',
        'china', 'chinese', 'usa', 'american', 'russia', 'russian', 'pakistan',
        'january', 'february', 'march', 'april', 'may', 'june', 'july',
        'august', 'september', 'october', 'november', 'december',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        
        // Generic abbreviations (not policy acronyms)
        'ut', 'iti', 'nit', 'iit', 'nit', 'iisc', 'bits',
        'arc', 'bot', 'ceo', 'cfo', 'cto', 'coo', 'vp', 'svp', 'evp',
        'ltd', 'pvt', 'inc', 'llp', 'llc', 'corp', 'co',
        
        // Major Indian cities (noise in keyword extraction)
        'delhi', 'mumbai', 'bangalore', 'bengaluru', 'chennai', 'kolkata',
        'hyderabad', 'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur',
        'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 'patna',
        'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad',
        'meerut', 'rajkot', 'varanasi', 'srinagar', 'aurangabad', 'dhanbad',
        'amritsar', 'allahabad', 'prayagraj', 'ranchi', 'howrah', 'coimbatore',
        'jabalpur', 'gwalior', 'vijayawada', 'jodhpur', 'madurai', 'raipur',
        'kochi', 'chandigarh', 'gurgaon', 'gurugram', 'noida', 'greater',
    ]);

    // ============================================
    // SYNONYM MAPPING (for deduplication)
    // ============================================
    const SYNONYMS = {
        'reserve bank': 'RBI',
        'reserve bank of india': 'RBI',
        'sebi': 'SEBI',
        'securities exchange': 'SEBI',
        'gst': 'GST',
        'goods services tax': 'GST',
        'goods and services tax': 'GST',
        'upi': 'UPI',
        'unified payments': 'UPI',
        'unified payments interface': 'UPI',
        'digital rupee': 'CBDC',
        'central bank digital currency': 'CBDC',
        'npa': 'NPA',
        'non performing asset': 'NPA',
        'non-performing asset': 'NPA',
        'bad loan': 'NPA',
        'fdi': 'FDI',
        'foreign direct investment': 'FDI',
        'fpi': 'FPI',
        'foreign portfolio': 'FPI',
        'startup india': 'Startup India',
        'start-up india': 'Startup India',
        'make in india': 'Make in India',
        'digital india': 'Digital India',
        'pli scheme': 'PLI Scheme',
        'production linked incentive': 'PLI Scheme',
        'production-linked incentive': 'PLI Scheme',
        'lok sabha': 'Lok Sabha',
        'lower house': 'Lok Sabha',
        'rajya sabha': 'Rajya Sabha',
        'upper house': 'Rajya Sabha',
        'dpdp': 'DPDP Act',
        'dpdpa': 'DPDP Act',
        'data protection act': 'DPDP Act',
        'digital personal data protection': 'DPDP Act',
        'electric vehicle': 'EV',
        'electric vehicles': 'EV',
        'ev policy': 'EV Policy',
        'msme': 'MSME',
        'micro small medium': 'MSME',
        'small business': 'MSME',
        'sme': 'MSME',
    };

    // ============================================
    // PERSON NAME PATTERNS
    // ============================================
    const PERSON_NAME_PATTERNS = [
        // Common Indian name patterns
        /^(shri|smt|mr|mrs|ms|dr|prof)\s+\w+/i,
        // Names with common suffixes
        /\w+(kumar|sharma|singh|gupta|patel|reddy|rao|iyer|nair|menon|pillai|verma|jain|agarwal|agrawal|joshi|mehta|shah|das|roy|sen|bose|mukherjee|chatterjee|banerjee)$/i,
        // Single capitalized words that look like names
        /^[A-Z][a-z]+$/,
    ];

    // ============================================
    // CATEGORY MAPPINGS
    // ============================================
    // ⚡ Civil Liberties is a PRIORITY category - PolicyRadar pays extra attention to fundamental rights
    const KEYWORD_CATEGORIES = {
        'Finance & Banking': [
            'RBI', 'SEBI', 'bank', 'banking', 'loan', 'credit', 'NPA', 'NBFC',
            'monetary', 'interest rate', 'repo', 'inflation', 'liquidity',
            'deposit', 'lending', 'fintech', 'payment', 'UPI', 'digital payment'
        ],
        'Taxation': [
            'GST', 'tax', 'taxation', 'income tax', 'direct tax', 'indirect tax',
            'TDS', 'TCS', 'ITR', 'assessment', 'CBDT', 'CBIC', 'customs', 'duty'
        ],
        'Trade & Commerce': [
            'export', 'import', 'trade', 'tariff', 'FTA', 'SEZ', 'DGFT',
            'foreign trade', 'commerce', 'WTO', 'dumping', 'safeguard'
        ],
        'Digital & Technology': [
            'digital', 'technology', 'IT', 'software', 'data', 'cyber', 'AI',
            'startup', 'fintech', 'e-commerce', 'internet', 'telecom', '5G',
            'semiconductor', 'electronics', 'data centre', 'cloud'
        ],
        'Infrastructure': [
            'infrastructure', 'highway', 'road', 'rail', 'railway', 'airport',
            'port', 'metro', 'smart city', 'construction', 'PPP', 'NHAI'
        ],
        'Energy & Environment': [
            'energy', 'power', 'electricity', 'renewable', 'solar', 'wind',
            'oil', 'gas', 'coal', 'green', 'carbon', 'climate', 'environment',
            'pollution', 'EV', 'electric vehicle', 'hydrogen'
        ],
        'Labour & Employment': [
            'labour', 'labor', 'employment', 'worker', 'wage', 'EPFO', 'ESIC',
            'gig', 'contract', 'industrial', 'factory', 'union', 'strike'
        ],
        'Healthcare': [
            'health', 'healthcare', 'hospital', 'medical', 'pharma', 'drug',
            'PMJAY', 'ayushman', 'insurance', 'FSSAI', 'food safety'
        ],
        'Education': [
            'education', 'university', 'school', 'college', 'UGC', 'AICTE',
            'NEP', 'skill', 'training', 'NEET', 'JEE', 'IIT', 'IIM'
        ],
        'Agriculture': [
            'agriculture', 'farmer', 'farming', 'crop', 'MSP', 'APMC', 'FPO',
            'irrigation', 'fertilizer', 'pesticide', 'agri', 'rural'
        ],
        'Corporate & Securities': [
            'company', 'corporate', 'IPO', 'stock', 'share', 'equity', 'bond',
            'merger', 'acquisition', 'FDI', 'FPI', 'investment', 'PE', 'VC'
        ],
        'Governance & Politics': [
            'parliament', 'lok sabha', 'rajya sabha', 'election', 'governor',
            'legislation', 'bill', 'act', 'ordinance', 'constitutional', 'CAG'
        ],
        'Civil Liberties': [
            'fundamental rights', 'article 19', 'article 21', 'article 14',
            'freedom of speech', 'freedom of expression', 'free speech',
            'right to protest', 'right to assemble', 'protest ban', 'section 144',
            'internet shutdown', 'sedition', 'uapa', 'preventive detention',
            'habeas corpus', 'personal liberty', 'custodial death', 'custodial torture',
            'nhrc', 'human rights', 'press freedom', 'censorship', 'religious freedom',
            'minority rights', 'dissent', 'civil society', 'fcra'
        ]
    };

    // ============================================
    // MAIN EXTRACTION FUNCTION
    // ============================================
    function extractKeywords(text, options = {}) {
        const {
            maxKeywords = 20,
            minWordLength = 3,
            includeCategories = true,
            filterPersonNames = true,
            normalizeSynonyms = true,
        } = options;

        if (!text || typeof text !== 'string') {
            return [];
        }

        const results = new Map();

        // Step 1: Extract multi-word phrases first
        const phrases = extractPhrases(text);
        phrases.forEach(phrase => {
            const normalized = normalizeSynonyms ? 
                (SYNONYMS[phrase.toLowerCase()] || phrase) : phrase;
            const key = normalized.toLowerCase();
            if (!results.has(key)) {
                results.set(key, {
                    keyword: normalized,
                    count: 1,
                    type: 'phrase',
                    category: includeCategories ? categorizeKeyword(normalized) : null
                });
            } else {
                results.get(key).count++;
            }
        });

        // Step 2: Extract single words
        const words = text
            .toLowerCase()
            .replace(/[^\w\s-]/g, ' ')
            .split(/\s+/)
            .filter(word => 
                word.length >= minWordLength &&
                !STOPWORDS.has(word) &&
                !/^\d+$/.test(word)
            );

        words.forEach(word => {
            // Skip if it's part of an already-extracted phrase
            const isPartOfPhrase = Array.from(results.values()).some(
                r => r.type === 'phrase' && r.keyword.toLowerCase().includes(word)
            );
            if (isPartOfPhrase) return;

            // Skip person names if filtering enabled
            if (filterPersonNames && isPersonName(word)) return;

            const normalized = normalizeSynonyms ?
                (SYNONYMS[word] || word) : word;
            const key = normalized.toLowerCase();

            if (!results.has(key)) {
                results.set(key, {
                    keyword: formatKeyword(normalized),
                    count: 1,
                    type: 'word',
                    category: includeCategories ? categorizeKeyword(normalized) : null
                });
            } else {
                results.get(key).count++;
            }
        });

        // Step 3: Extract and add acronyms
        const acronyms = extractAcronyms(text);
        acronyms.forEach(acr => {
            const key = acr.toLowerCase();
            if (!results.has(key)) {
                results.set(key, {
                    keyword: acr,
                    count: 1,
                    type: 'acronym',
                    expansion: ACRONYMS[acr] || null,
                    category: includeCategories ? categorizeKeyword(acr) : null
                });
            } else {
                results.get(key).count++;
            }
        });

        // Sort by count and return top N
        return Array.from(results.values())
            .sort((a, b) => b.count - a.count)
            .slice(0, maxKeywords);
    }

    // ============================================
    // HELPER FUNCTIONS
    // ============================================

    function extractPhrases(text) {
        const found = [];
        const lowerText = text.toLowerCase();

        POLICY_PHRASES.forEach(phrase => {
            const lowerPhrase = phrase.toLowerCase();
            let index = 0;
            while ((index = lowerText.indexOf(lowerPhrase, index)) !== -1) {
                found.push(phrase);
                index += phrase.length;
            }
        });

        return found;
    }

    function extractAcronyms(text) {
        const found = [];
        const pattern = /\b([A-Z]{2,6})\b/g;
        let match;

        while ((match = pattern.exec(text)) !== null) {
            const acr = match[1];
            if (ACRONYMS[acr] || isKnownAcronym(acr)) {
                found.push(acr);
            }
        }

        return found;
    }

    function isKnownAcronym(text) {
        return Object.keys(ACRONYMS).includes(text.toUpperCase());
    }

    function isPersonName(word) {
        return PERSON_NAME_PATTERNS.some(pattern => pattern.test(word));
    }

    function formatKeyword(word) {
        // Capitalize first letter for display
        if (word.length <= 4 && word === word.toUpperCase()) {
            return word; // Keep acronyms uppercase
        }
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    }

    function categorizeKeyword(keyword) {
        const lower = keyword.toLowerCase();
        
        for (const [category, terms] of Object.entries(KEYWORD_CATEGORIES)) {
            if (terms.some(term => 
                lower.includes(term.toLowerCase()) ||
                term.toLowerCase().includes(lower)
            )) {
                return category;
            }
        }
        
        return 'Governance';
    }

    // ============================================
    // PUBLIC API
    // ============================================
    return {
        extractKeywords,
        extractPhrases,
        extractAcronyms,
        isPersonName,
        categorizeKeyword,
        
        // Expose data for external use
        POLICY_PHRASES,
        ACRONYMS,
        STOPWORDS,
        SYNONYMS,
        KEYWORD_CATEGORIES,
        
        // Utility functions
        normalizeKeyword: (keyword) => SYNONYMS[keyword.toLowerCase()] || keyword,
        expandAcronym: (acronym) => ACRONYMS[acronym.toUpperCase()] || null,
        isStopword: (word) => STOPWORDS.has(word.toLowerCase()),
    };
})();

// Export for Node.js environments
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PolicyKeywords;
}
