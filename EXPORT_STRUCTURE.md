# Recommended Meta Ads export structure

Create three saved export presets: Campaigns, Ad sets and Ads.

## 1. Campaign export

Required identity and hierarchy:

- Campaign ID
- Campaign name

Required period and delivery:

- Reporting starts
- Reporting ends
- Delivery
- Created date
- Last edited date

Required performance:

- Results
- Result indicator
- Cost per result
- Amount spent
- Impressions
- Reach
- Frequency
- CPM
- Link clicks
- Link CTR
- CPC
- Landing page views
- Cost per landing page view
- Attribution setting

## 2. Ad-set export

Required identity and hierarchy:

- Campaign ID
- Campaign name
- Ad set ID
- Ad set name

Required period and delivery:

- Reporting starts
- Reporting ends
- Delivery
- Start
- End
- Created date
- Last edited date

Required budget and performance:

- Ad set budget
- Budget type
- Results
- Result indicator
- Cost per result
- Amount spent
- Impressions
- Reach
- Frequency
- CPM
- Link clicks
- Link CTR
- CPC
- Landing page views
- Cost per landing page view
- Attribution setting

## 3. Ad export

Required identity and hierarchy:

- Campaign ID
- Campaign name
- Ad set ID
- Ad set name
- Ad ID
- Ad name

Required period and delivery:

- Reporting starts
- Reporting ends
- Delivery
- Created date
- Last significant edit

Required performance:

- Results
- Result indicator
- Cost per result
- Amount spent
- Impressions
- Reach
- Frequency
- CPM
- Link clicks
- Link CTR
- CPC
- Landing page views
- Cost per landing page view
- Quality ranking
- Engagement-rate ranking
- Conversion-rate ranking
- Attribution setting

## What is already correct in the supplied files

- Reporting start and end dates are present.
- Campaign, ad-set and ad names are present.
- The ad export now includes the ad-set name.
- Spend, results, cost per result, impressions, reach, frequency, clicks, CTR and CPC are present.

## What still needs to be added

Highest priority:

1. Campaign ID in all three exports.
2. Campaign name in the ad-set and ad exports.
3. Ad set ID in the ad-set and ad exports.
4. Ad ID in the ad export.
5. Landing page views and cost per landing page view.
6. Created date in the ad export.

The IDs are more important than names. Names can be edited; IDs remain stable.
