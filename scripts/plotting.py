# plotting.py

import plotly.express as px

def plot_pie_chart(df, values, names, title, output_file):
    fig = px.pie(df, values=values, names=names, title=title)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.show()
    fig.write_image(output_file)
