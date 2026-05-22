def placeholders_sql(valores):
    return ', '.join('?' for _ in valores)
