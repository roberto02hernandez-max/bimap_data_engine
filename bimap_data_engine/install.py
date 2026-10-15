from bimap_data_engine.custom_fields import sync_custom_fields
from bimap_data_engine.workspace import sync_buying_workspace


def after_install():
	sync_custom_fields()
	sync_buying_workspace()


def after_migrate():
	sync_custom_fields()
	sync_buying_workspace()

