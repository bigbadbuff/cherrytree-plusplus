/*
 * ct_templates.h
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

#include "ct_treestore.h"
#include <map>
#include <string>
#include <vector>

class CtMainWin;

// CherryTree++: Notion-style templates. The children of a top-level node named "Templates" are
// templates; instantiating one copies it (with its subnodes) and fills {{title}}, {{date}} and
// {{time}} placeholders in node names and text.
namespace CtTemplates {

using Values = std::map<std::string, Glib::ustring>;

// {{title}} = title, {{date}} = YYYY-MM-DD, {{time}} = HH:MM (now)
Values default_values(const Glib::ustring& title);

// Replace {{key}} placeholders that have a value; unknown placeholders are left as they are
Glib::ustring fill(const Glib::ustring& text, const Values& values);

// Same as fill() on a text buffer, keeping the formatting of each placeholder for its value
void fill_buffer(const Glib::RefPtr<Gtk::TextBuffer>& buffer, const Values& values);

// The top-level node named "Templates" (case-insensitive); an invalid iter if there is none
CtTreeIter templates_root(CtTreeStore& tree_store);

// The templates: children of templates_root(), in tree order
std::vector<CtTreeIter> templates(CtTreeStore& tree_store);

// Whether the node is the Templates node or one of its descendants
bool is_within_templates(CtTreeStore& tree_store, const CtTreeIter& iter);

// Copy the template subtree after the selected node (or after the Templates node when the
// selection is inside it), name the copy values["title"] and fill the placeholders.
// Returns the new top node, which becomes the selected node.
Gtk::TreeModel::iterator instantiate(CtMainWin* pCtMainWin, CtTreeIter template_iter, const Values& values);

} // namespace CtTemplates
