Data Analysis Process

1. Problem definition  
2. Data definition and requirements  
3. Data discovery / source identification  
4. Data acquisition  
   1. Structure and clean the data to work in your pipeline (Extract, Transform, Load)  
5. Data understanding / review  
6. Exploratory data analysis  
7. Refine questions and assumptions  
8. Build a data model and verify it

Full MVP that can be shipped to customers

1. Problem definition  
2. Data definition and requirements  
3. Data discovery / source identification  
4. Data acquisition  
5. Data understanding / review  
6. Exploratory data analysis  
7. Refine questions and assumptions  
8. Structure and clean the data to work in your pipeline (Extract, Transform, Load)  
9. Build a data model and verify it  
10. Build MVP software  
    1. Choose 1-2 features to create  
       1. It won’t answer every scenario  
       2. It won’t be a digital twin  
       3. It will provide limited insight that customers deem valuable enough to pay for  
    2. Setup Github repo  
    3. Build backend  
       1. Match software architecture with data structure and requirements  
       2. Write code  
       3. Check edge cases  
       4. Automate tests  
       5. Manual test anything that can’t be automated  
    4. Build frontend  
       1. Match frontend requirements to backend needs  
       2. Design frontend interactions  
       3. Test frontend interactions with users  
       4. Write code for the frontend  
       5. Test code for the frontend (including multiple browsers and formats)  
       6. Test frontend interaction with users again  
    5. Connect backend to front end

Goal A: Create a real commercial product that grid operators and planners would dream of for offshore wind integration

* Data analysis process  
  * Regulations  
  * Structure and clean tens or even hundreds of data sources  
  * Transmission and distribution losses  
  * Spatial data  
  * Flow directions  
  * Multiple generative resources  
  * Load forecasting with historical data is less reliable  
  * New additions to the grid are shifting demand profiles  
  * Energy can be traded from one grid to another  
  * EVs create higher demand late into the evening  
  * Behind-the-meter solar  
  * Heatpumps  
  * Market simulations  
  * Optimization engines  
  * Forecasting models  
* Barriers  
  * Highly regulated industry  
  * There is no national data standard across all states and organizations  
  * Grid operators are slow to change, they’re used to planning 10 to 15 years in advance  
  * Grid operators have to consider increasing transmission which takes a minimum of 8 years to complete, while a data center can come online in just 2-3 years  
  * Grid operators already use between 10-20 tools  
  * Many smaller grids are under budget constraints

Goal B: Create a small sliver of a commercial product that grid operators and planners might take interest on (e.g., optimization of dispatchable offshore wind power with batteries or a predictive tool for what datacenters will be built and where)

* Data analysis process  
  * Structure and clean 2-4 data sources  
  * Choose either a small geographic area or high-level geographic region with low complexity  
  * Initially simplify the entire system to only the key points of data that communicate the problem and solution then add pieces back in if time allows  
    * No spatial data  
    * No transmission and distribution losses  
    * No flow directions  
    * No interchange between markets  
    * No regulatory considerations  
    * No edge cases

Goal C: Create a scenario explorer that demonstrates understanding of a problem grid operators or planners may face to educate the public. It still demonstrates the ability to analyze and interpret data real grid operators or planners are faced with.

* Data analysis process  
  * Structure and clean 2-4 data sources  
  * Choose either a small geographic area or high-level geographic region with low complexity  
  * Leave everything out except the key points of data that communicate the problem and solution  
  * Provide additional information for each scenario if a user wants to explore further