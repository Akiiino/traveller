from classes import Guide, POI

points = {
    "1": POI(
        name="test_point",
        description="funy",
        latitude=1.5,
        longitude=2.5,
        visited=True,
        category="See",
        link="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
}

categories = {
    "See": {"color": "#00842b", "icon": "special_photo_camera"},
    "Sleep": {"color": "#1010a0", "icon": "tourism_hotel"},
    "Do": {"color": "#00842b", "icon": "special_photo_camera"},
    "Drink": {"color": "#d00d0d", "icon": "restaurants"},
    "Go": {"color": "#1010a0", "icon": "public_transport_stop_position"},
    "Eat": {"color": "#d00d0d", "icon": "restaurants"},
    "Buy": {"color": "#a71de1", "icon": "shop_department_store"},
}

guide = Guide("Korea Trip", "", categories=categories, points=points)
guide.to_zip("korea.zip")
