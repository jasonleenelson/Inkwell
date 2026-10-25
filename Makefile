# Install Inkwell for one user (the default) or system-wide:
#   make install                 -> ~/.local
#   sudo make install PREFIX=/usr/local
PREFIX ?= $(HOME)/.local
APP_ID = io.github.jasonleenelson.Inkwell
LIBDIR = $(PREFIX)/share/inkwell
PYTHON ?= python3
# The commit being installed, so Check for Updates knows what is new.
COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null)

.PHONY: run test install uninstall

run:
	$(PYTHON) -m inkwell

test:
	$(PYTHON) -m unittest discover -s tests -v

install:
	install -d $(DESTDIR)$(LIBDIR)/inkwell $(DESTDIR)$(PREFIX)/bin
	install -m 644 inkwell/*.py $(DESTDIR)$(LIBDIR)/inkwell/
	install -d $(DESTDIR)$(LIBDIR)/inkwell/icons
	install -m 644 inkwell/icons/*.svg $(DESTDIR)$(LIBDIR)/inkwell/icons/
	printf '#!/bin/sh\nPYTHONPATH="%s$${PYTHONPATH:+:$$PYTHONPATH}" exec %s -m inkwell "$$@"\n' \
		'$(LIBDIR)' '$(PYTHON)' > $(DESTDIR)$(PREFIX)/bin/inkwell
	chmod 755 $(DESTDIR)$(PREFIX)/bin/inkwell
	install -Dm 644 data/$(APP_ID).desktop \
		$(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	sed -i 's|^Exec=inkwell|Exec=$(PREFIX)/bin/inkwell|' \
		$(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	install -Dm 644 data/$(APP_ID).metainfo.xml \
		$(DESTDIR)$(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml
	install -Dm 644 data/icons/hicolor/scalable/apps/$(APP_ID).svg \
		$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
	@if [ -z "$(DESTDIR)" ]; then \
		printf 'source=%s\ncommit=%s\nprefix=%s\n' '$(CURDIR)' '$(COMMIT)' '$(PREFIX)' \
			> $(LIBDIR)/install-info; \
		command -v gtk4-update-icon-cache >/dev/null && \
			gtk4-update-icon-cache -qtf $(PREFIX)/share/icons/hicolor || true; \
		command -v update-desktop-database >/dev/null && \
			update-desktop-database -q $(PREFIX)/share/applications || true; \
	fi

uninstall:
	rm -rf $(DESTDIR)$(LIBDIR)
	rm -f $(DESTDIR)$(PREFIX)/bin/inkwell
	rm -f $(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	rm -f $(DESTDIR)$(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml
	rm -f $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
