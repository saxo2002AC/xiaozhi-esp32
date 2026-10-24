#ifndef KITTY_LOCKDOWN_H
#define KITTY_LOCKDOWN_H

// Mission Kitty lockdown: the device's only network peer is CONFIG_KITTY_SERVER_HOST.
// Every server-supplied destination (websocket url, MQTT endpoint, MQTT UDP server, vision explain
// url, notify audio url) goes through this file before it is stored or used. The host rule lives in
// one place: KittyHostAllowed().

#include <sdkconfig.h>

#ifdef CONFIG_KITTY_LOCKDOWN

#include <string_view>

namespace kitty {

// Exact match only: no DNS names, no suffix or prefix tricks.
inline bool KittyHostAllowed(std::string_view host) {
    return host == std::string_view(CONFIG_KITTY_SERVER_HOST);
}

// Optional ":<digits>" after the host; nothing else.
inline bool SplitHostPort(std::string_view authority, std::string_view& host) {
    auto colon = authority.find(':');
    host = authority.substr(0, colon);
    if (colon == std::string_view::npos) {
        return true;
    }
    auto port = authority.substr(colon + 1);
    if (port.empty() || port.size() > 5) {
        return false;
    }
    for (char c : port) {
        if (c < '0' || c > '9') {
            return false;
        }
    }
    return true;
}

// True only for "http://" or "ws://" URLs whose host is CONFIG_KITTY_SERVER_HOST.
// Rejects https/wss/mqtt and any other scheme, userinfo ("user@host"), and malformed ports.
inline bool KittyUrlAllowed(std::string_view url) {
    std::string_view rest;
    if (url.substr(0, 7) == "http://") {
        rest = url.substr(7);
    } else if (url.substr(0, 5) == "ws://") {
        rest = url.substr(5);
    } else {
        return false;
    }
    auto end = rest.find_first_of("/?#");
    auto authority = rest.substr(0, end);
    if (authority.find('@') != std::string_view::npos) {
        return false;
    }
    std::string_view host;
    return SplitHostPort(authority, host) && KittyHostAllowed(host);
}

// MQTT endpoints are "host[:port]" and the UDP server is a bare host, not URLs.
inline bool KittyEndpointAllowed(std::string_view host_port) {
    if (host_port.find_first_of("/@?#") != std::string_view::npos) {
        return false;
    }
    std::string_view host;
    return SplitHostPort(host_port, host) && KittyHostAllowed(host);
}

}  // namespace kitty

#endif  // CONFIG_KITTY_LOCKDOWN

#endif  // KITTY_LOCKDOWN_H
