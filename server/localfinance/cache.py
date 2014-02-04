from dogpile.cache import make_region

region = make_region().configure(
    'dogpile.cache.dbm',
    expiration_time = 3600*24*31,
    arguments = {
        "filename":"./cachefile.dbm"
    }
)
