import json
import plotly.graph_objects as go
import pandas as pd
import geopandas as gpd
import streamlit as st


geojson_quartiers_path = "data/stzh.adm_statistische_quartiere_v.json"
data_zurich_inhabitants = "data/zurich_quartier_population_2024.csv"
data_zurich_income = "data/income_zurich_quartiers_1k.csv"
data_zurich_stores = "data/combined_zurich_supermarkets_total.csv"
data_zurich_inhabitants_density = "data/zh_population_quartiers_density.csv"

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


st.title("Attractiveness Index for Migros in Zürich City by Districts")


st.sidebar.header("Weights configuration")

st.sidebar.markdown("### Positive Factors (sum = 1)")
w1 = st.sidebar.slider("Weight for Population Density (w1)", 0.0, 1.0, 0.5, 0.01)
w2 = 1.0 - w1
st.sidebar.write(f"Weight for Income (w2): {w2:.2f}")


st.sidebar.markdown("---")
st.sidebar.markdown("### Negative Factors (sum = 1)")
w3 = st.sidebar.slider("Weight for Competition (w3)", 0.0, 1.0, 0.5, 0.01)
w4 = 1.0 - w3
st.sidebar.write(f"Weight for Migros Density (w4): {w4:.2f}")

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Final weights:** w1={w1:.2f}, w2={w2:.2f}, w3={w3:.2f}, w4={w4:.2f}"
)

store_counts = (
    df_stores.groupby(['district', 'group'])
    .size()
    .unstack(fill_value=0)
    .reset_index()
    .rename(columns={
        'district': 'Quartier',
        'competitors': 'Competition',
        'migros_group': 'MigrosDensity'
    })
)

df_merged = (
    df_population_quartier[['Quartier', 'density_inh_per_km2']]
    .merge(df_income, on='Quartier', how='left')
    .merge(store_counts, on='Quartier', how='left')
)
df_merged[['Competition', 'MigrosDensity']] = df_merged[['Competition', 'MigrosDensity']].fillna(0)


for col in ['density_inh_per_km2', 'Income_1kCHF', 'Competition', 'MigrosDensity']:
    df_merged[col + '_norm'] = (df_merged[col] - df_merged[col].min()) / (df_merged[col].max() - df_merged[col].min())

df_merged['AI'] = (
    w1 * df_merged['density_inh_per_km2_norm']
    + w2 * df_merged['Income_1kCHF_norm']
    - w3 * df_merged['Competition_norm']
    - w4 * df_merged['MigrosDensity_norm']
)

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
        # titleside="right",
        # titlefont=dict(size=14),
        # tickfont=dict(size=12)
    )
))

fig.add_trace(go.Scattermap(
    lat=df_stores.loc[df_stores['group']=='migros_group','lat'],
    lon=df_stores.loc[df_stores['group']=='migros_group','lng'],
    mode='markers',
    marker=dict(size=9, color='orange'),
    name='🟧 Migros Group stores'
))
fig.add_trace(go.Scattermap(
    lat=df_stores.loc[df_stores['group']=='competitors','lat'],
    lon=df_stores.loc[df_stores['group']=='competitors','lng'],
    mode='markers',
    marker=dict(size=9, color='blue'),
    name='🟦 Competitor stores'
))

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
st.text("Map showing Migros Group and Competitors stores")



df_result = df_merged[['Quartier', 'AI']].sort_values(by='AI', ascending=False)

st.text("")
st.text("")
st.text("")

st.subheader("Top 10 Districts by Attractiveness Index (AI)")
st.dataframe(df_result.head(10), use_container_width=True)