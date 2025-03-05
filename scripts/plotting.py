# plotting.py

import plotly.express as px


def plot_pie_chart(df, values, names, title, output_file):
    """
    Plot a pie chart from a DataFrame and save it as an image to the output file.
    :param df: DataFrame containing the data.
    :param values: Values to plot in the pie chart.
    :param names: Names to plot in the pie chart.
    :param title: Title of the pie chart.
    :param output_file: Output file path to save the pie chart image.
    :return: Returns a pie chart image saved in the output file.
    """
    fig = px.pie(df, values=values, names=names, title=title)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.show()
    fig.write_image(output_file)