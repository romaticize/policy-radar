// assets/js/main.js

document.addEventListener('DOMContentLoaded', () => {
    const categoriesContainer = document.getElementById('categories-container');
    const loader = document.getElementById('loader');
    const errorMessage = document.getElementById('error-message');
    const lastUpdatedElem = document.getElementById('last-updated');
    const searchInput = document.getElementById('search-input');
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    
    const DATA_URL = 'data/public_data.json';
    let allArticles = [];

    async function fetchData() {
        try {
            const response = await fetch(`${DATA_URL}?v=${new Date().getTime()}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            
            const data = await response.json();
            // Use the article data from the new JSON structure
            allArticles = data.articles.map(article => ({
                ...article,
                // The new engine provides a date, so we parse it
                publication_date: new Date(article.publication_date) 
            }));
            
            displayContent(allArticles);
            updateMetadata(data.last_updated);
            loader.style.display = 'none';
        } catch (error) {
            console.error("Failed to fetch policy data:", error);
            loader.style.display = 'none';
            errorMessage.style.display = 'block';
        }
    }

    function displayContent(articles) {
        categoriesContainer.innerHTML = '';
        if (articles.length === 0) {
            categoriesContainer.innerHTML = '<p class="error-message">No articles match your search.</p>';
            return;
        }

        // Group articles by category, similar to your original script
        const articlesByCategory = articles.reduce((acc, article) => {
            // The new engine doesn't provide a category, so we'll use the source for now
            // This can be updated once the engine provides categories
            const category = article.source_name; 
            if (!acc[category]) {
                acc[category] = [];
            }
            acc[category].push(article);
            return acc;
        }, {});

        // Sort categories alphabetically
        const sortedCategories = Object.keys(articlesByCategory).sort();

        sortedCategories.forEach(category => {
            const categorySection = document.createElement('section');
            categorySection.className = 'category-section';

            const articlesHtml = articlesByCategory[category]
                .map(article => createArticleCard(article))
                .join('');

            categorySection.innerHTML = `
                <h2 class="category-title">
                    <span>${getCategoryIcon(category)}</span>
                    ${category}
                </h2>
                <div class="article-grid">
                    ${articlesHtml}
                </div>
            `;
            categoriesContainer.appendChild(categorySection);
        });
    }

    function createArticleCard(article) {
        const publishedDate = article.publication_date.toLocaleDateString('en-GB', {
            day: 'numeric', month: 'short', year: 'numeric'
        });
        
        // The new engine doesn't have a relevance score yet, so we'll omit the priority class
        // This can be added back once scoring is implemented in the engine
        const priorityClass = ''; 

        return `
            <div class="article-card ${priorityClass}">
                <div class="article-header">
                    <span class="article-source">${article.source_name}</span>
                    <span class="article-date">${publishedDate}</span>
                </div>
                <h3 class="article-title">
                    <a href="${article.url}" target="_blank" rel="noopener noreferrer">${article.title}</a>
                </h3>
                <p class="article-summary">${article.title}</p> <!-- Using title as summary for now -->
            </div>
        `;
    }

    function updateMetadata(lastUpdatedISO) {
        const lastUpdatedDate = new Date(lastUpdatedISO);
        lastUpdatedElem.textContent = `Last Updated: ${lastUpdatedDate.toLocaleString('en-GB')}`;
        document.getElementById('year').textContent = new Date().getFullYear();
    }

    function handleSearch() {
        const query = searchInput.value.toLowerCase();
        const filteredArticles = allArticles.filter(article => 
            article.title.toLowerCase().includes(query) ||
            article.source_name.toLowerCase().includes(query)
        );
        displayContent(filteredArticles);
    }

    function getCategoryIcon(category) {
        // A simple hashing function to get a consistent emoji for each source
        let hash = 0;
        for (let i = 0; i < category.length; i++) {
            hash = category.charCodeAt(i) + ((hash << 5) - hash);
        }
        const emojis = ['📄', '📑', '📈', '⚖️', '🏛️', '🌐', '🔬', '💡'];
        return emojis[Math.abs(hash) % emojis.length];
    }
    
    function toggleTheme() {
        const body = document.body;
        const currentTheme = body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        body.setAttribute('data-theme', newTheme);
        themeIcon.textContent = newTheme === 'dark' ? '☀️' : '🌙';
        localStorage.setItem('theme', newTheme);
    }

    function loadTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.body.setAttribute('data-theme', savedTheme);
        themeIcon.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
    }

    // Event Listeners
    searchInput.addEventListener('input', handleSearch);
    themeToggle.addEventListener('click', toggleTheme);

    // Initial load
    loadTheme();
    fetchData();
});
