/*
 * ct_backlinks.h
 *
 * Copyright 2009-2025
 * Giuseppe Penone <giuspen@gmail.com>
 * Evgenii Gurianov <https://github.com/txe>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
 * MA 02110-1301, USA.
 */

#pragma once

#include <glibmm/ustring.h>
#include <optional>
#include <vector>

class CtTreeStore;

// CherryTree++: Notion-style backlinks ("which nodes link to this one").
namespace CtBacklinks {

// Node id targeted by a link tag name such as "link_node 12 anchor"; nullopt for any other tag
std::optional<gint64> node_id_from_link_tag(const Glib::ustring& tag_name);

// Nodes whose rich text links to the target (or to any clone of it), in tree order. Clones are
// reported once, by the id of the node holding their content; the target itself is excluded.
std::vector<gint64> linking_node_ids(CtTreeStore& tree_store, const gint64 target_node_id);

} // namespace CtBacklinks
