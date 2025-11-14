import json
import plotly.graph_objects as go
import pandas as pd
import geopandas as gpd
import streamlit as st
from shapely.geometry import Point

# File paths
geojson_quartiers_path = "data/stzh.adm_statistische_quartiere_v.json"
data_zurich_inhabitants = "data/zurich_quartier_population_2024.csv"
data_zurich_income = "data/income_zurich_quartiers_1k.csv"
data_zurich_stores = "data/supermarkets_without_dublicates.csv"
data_zurich_inhabitants_density = "data/zh_population_quartiers_density.csv"

# Load data
df_population = pd.read_csv(data_zurich_inhabitants)
with open(geojson_quartiers_path, 'r') as file:
    quartiers_geojson = json.load(file)
df_income = pd.read_csv(data_zurich_income)
df_stores = pd.read_csv(data_zurich_stores)


gdf_quartiere = gpd.read_file(geojson_quartiers_path)
gdf = gdf_quartiere.merge(df_population, left_on="qname", right_on="Quartier")
gdf = gdf.to_crs(2056)
gdf["area_km2"] = gdf.geometry.area / 1e6
gdf["density_inh_per_km2"] = gdf["Inhabitants"] / gdf["area_km2"]

df_population_quartier = gdf[["qname", "qnr", "kname", "knr", "Quartier",
                              "Inhabitants", "area_km2", "density_inh_per_km2"]].copy()
df_population_quartier.to_csv(data_zurich_inhabitants_density, index=False)

# Prepare GeoDataFrame for stores
gdf_stores = gpd.GeoDataFrame(
    df_stores,
    geometry=[Point(xy) for xy in zip(df_stores["lng"], df_stores["lat"])],
    crs="EPSG:4326"
)

gdf_quartiere = gdf_quartiere.to_crs("EPSG:4326")

if 'index_right' in gdf_stores.columns:
    gdf_stores = gdf_stores.drop(columns=['index_right'])

# Spatial join to find stores within Zürich city districts
gdf_stores_in_city = gpd.sjoin(
    gdf_stores,
    gdf_quartiere[['qname', 'geometry']], 
    how="inner",
    predicate="within"
)

# Rename column for clarity
gdf_stores_in_city = gdf_stores_in_city.rename(columns={'qname': 'Quartier'}).reset_index(drop=True)
# gdf_stores_in_city = gdf_stores_in_city.drop_duplicates(subset=['lat', 'lng'])

st.set_page_config(layout="wide",page_icon="data/migros-icon.png")
st.title("Attractiveness Index for Migros in Zürich City by Districts")

st.sidebar.header("Weights configuration")


# Setup weight sliders
independent_mode = st.sidebar.toggle("Use independent weights (0–0.5 each)", value=False)

if not independent_mode:
    st.sidebar.markdown("### Positive Factors (sum = 0.5)")
    w1 = st.sidebar.slider("Weight for Population Density (w1)", 0.0, 0.5, 0.3, 0.01)
    w2 = 0.5 - w1
    st.sidebar.write(f"Weight for Income (w2): {w2:.2f}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Negative Factors (sum = 5)")
    w3 = st.sidebar.slider("Weight for Competition (w3)", 0.0, 0.5, 0.1, 0.01)
    w4 = 0.5 - w3
    st.sidebar.write(f"Weight for Migros Density (w4): {w4:.2f}")

else:
    st.sidebar.markdown("### Independent Weights (each 0–0.5)")
    w1 = st.sidebar.slider("Weight for Population Density (w1)", 0.0, 0.5, 0.25, 0.01)
    w2 = st.sidebar.slider("Weight for Income (w2)", 0.0, 0.5, 0.25, 0.01)
    w3 = st.sidebar.slider("Weight for Competition (w3)", 0.0, 0.5, 0.25, 0.01)
    w4 = st.sidebar.slider("Weight for Migros Density (w4)", 0.0, 0.5, 0.25, 0.01)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Final weights:** w1={w1:.2f}, w2={w2:.2f}, w3={w3:.2f}, w4={w4:.2f}"
)

# Weighted store counts by size
competitors_weighted = (
    gdf_stores_in_city[gdf_stores_in_city['group'] == 'competitors']
    .groupby('Quartier')['size']
    .sum()
    .reset_index(name='Competition')
)

migros_weighted = (
    gdf_stores_in_city[gdf_stores_in_city['group'] == 'migros_group']
    .groupby('Quartier')['size']
    .sum()
    .reset_index(name='MigrosDensity')
)


df_merged = (
    df_population_quartier[['Quartier', 'density_inh_per_km2']]
    .merge(df_income, on='Quartier', how='left')
    .merge(competitors_weighted, on='Quartier', how='left')
    .merge(migros_weighted, on='Quartier', how='left')
)

df_merged[['Competition', 'MigrosDensity']] = df_merged[['Competition', 'MigrosDensity']].fillna(0)

# Normalize values
for col in ['density_inh_per_km2', 'Income_1kCHF', 'Competition', 'MigrosDensity']:
    df_merged[col + '_norm'] = (df_merged[col] - df_merged[col].min()) / (df_merged[col].max() - df_merged[col].min())

# AI = (w1 * PopDensity + w2 * Income) - (w3 * Competition + w4 * MigrosDensity)
df_merged['AI'] = (
    w1 * df_merged['density_inh_per_km2_norm']
    + w2 * df_merged['Income_1kCHF_norm']
    - w3 * df_merged['Competition_norm']
    - w4 * df_merged['MigrosDensity_norm']
)

# Create choropleth map
fig = go.Figure(go.Choroplethmap(
    geojson=quartiers_geojson,
    locations=df_merged['Quartier'],
    featureidkey='properties.qname',
    z=df_merged['AI'],
    colorscale="RdYlGn",
    zmin=df_merged['AI'].min(),
    zmax=df_merged['AI'].max(),
    marker_opacity=0.6,
    marker_line_width=0.3,
    hovertext=df_merged.apply(
        lambda row: (
            f"<b>{row['Quartier']}</b><br>"
            f"AI: {row['AI']:.3f}<br>"
            f"Density: {row['density_inh_per_km2']:,.0f}/km²<br>"
            f"Income: {row['Income_1kCHF']:.1f}k CHF<br>"
            f"Competitors: {int(row['Competition'])}<br>"
            f"Migros: {int(row['MigrosDensity'])}"
        ),
        axis=1
    ),
    hoverinfo="text",
    showscale=True,
    colorbar=dict(
        title="Attractiveness Index (AI)",
    )
))

# Add Migros store markers
fig.add_trace(go.Scattermap(
    lat=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='migros_group','lat'],
    lon=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='migros_group','lng'],
    mode='markers',
    marker=dict(size=9, color='orange', opacity=0.4),
    name='Migros Group stores',
    hovertext=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='migros_group'].apply(
        lambda row: f"🟧 {row['name']}: [{row['district']}]", axis=1,
    ),
    hoverinfo='text'
))

# Add competitor store markers
fig.add_trace(go.Scattermap(
    lat=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='competitors','lat'],
    lon=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='competitors','lng'],
    mode='markers',
    marker=dict(size=9, color='blue', opacity=0.4),
    name='Competitor stores',
    hovertext=gdf_stores_in_city.loc[gdf_stores_in_city['group']=='competitors'].apply(
        lambda row: f"🟦 {row['name']}: [{row['district']}]", axis=1
    ),
    hoverinfo='text'
))

# Update layout
fig.update_layout(
    map_style="carto-positron",
    map_zoom=11.25,
    map_center={"lat": 47.37316262234101, "lon": 8.539650401986833},
    margin={"r":0,"t":40,"l":0,"b":0},
    title={
        'text': "Attractiveness Index (AI) for Migros — Zürich City",
        'x': 0.5,
        'xanchor': 'center'
    },
    legend=dict(
        title="Store types",
        orientation="h",
        yanchor="bottom",
        y=0.01,
        xanchor="center",
        x=0.5,
        font=dict(size=12)
    ),
    height=700
)

st.plotly_chart(fig, use_container_width=True)


st.text("")
st.text("")
st.markdown('<p style="text-align: center;">Map showing Migros Group and Competitors stores</p>', unsafe_allow_html=True)
df_result = df_merged[['Quartier', 'AI']].sort_values(by='AI', ascending=False)

st.text("")
st.text("")
st.text("")

df_result_top10 = df_result.head(10).reset_index(drop=True)
df_result_top10.index = df_result_top10.index + 1

table_html = df_result_top10.to_html(index=True, escape=False)

styled_table = f"""
<div style="display: flex; justify-content: center;">
    <div style="width: 60%;">
        {table_html}
    </div>
</div>
<style>
    table {{
        width: 100%;
        border-collapse: collapse;
        text-align: center;
    }}
    table tr:nth-child(1),
    table tr:nth-child(2),
    table tr:nth-child(3) {{
        font-weight: bold;
        font-size: 22px;
    }}
</style>
"""

st.markdown('<h3 style="text-align: center;">Top 10 Districts by Attractiveness Index</h3>', unsafe_allow_html=True)
st.markdown(styled_table, unsafe_allow_html=True)


# print("All ponts", len(gdf_stores_in_city))
# unique_points = gdf_stores_in_city.drop_duplicates(subset=['lat', 'lng'])
# print("Unique points:", len(unique_points))
# print(gdf_stores_in_city['group'].value_counts())
# print(gdf_stores_in_city.groupby('Quartier').size())
