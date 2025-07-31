PolicyRadar
PolicyRadar is a free, open-source news aggregator that provides a curated feed of Indian policy and legislative updates. It monitors over 270 sources, including government websites, think tanks, media outlets, and legal publications, to deliver a concise and relevant overview of the latest developments.

This repository contains the code for the public-facing website hosted at policyradar.in.

How It Works
This website is a static site that fetches a single JSON data file (data/public_data.json). This data file is generated daily by a private, proprietary aggregation engine.

Public Repository (This one): Contains only the client-side code (HTML, CSS, JS) to display the news. It is intentionally simple and has no backend logic.

Private Repository: Contains the core aggregation engine, the list of 270+ sources, parsing algorithms, and scoring logic. This engine runs on a schedule and pushes the updated public_data.json to this public repository.

This hybrid public/private architecture allows us to offer a free, fast, and useful service to the public while protecting the core intellectual property of the aggregation engine.

Contributing
We welcome contributions to the user interface and user experience of the PolicyRadar website! If you have suggestions for UI improvements, bug fixes, or accessibility enhancements, please feel free to open an issue or submit a pull request.

Please note: We do not accept pull requests for the aggregation logic or source list in this repository, as they are managed in the private engine. However, you can suggest a new source by opening an issue.

License
The code for this website (HTML, CSS, JavaScript) is licensed under the MIT License. See the LICENSE file for details.

The aggregated data in data/public_data.json is the property of the original publishers.