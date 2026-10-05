/*
 * ct_backlinks.cc
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

#include "ct_backlinks.h"
#include "ct_actions.h"
#include "ct_const.h"
#include "ct_dialogs.h"
#include "ct_misc_utils.h"
#include "ct_main_win.h"
#include <set>

namespace {

// link tags are named "link_" + link value, and node links are valued "node <id>[ <anchor>]"
const Glib::ustring NODE_LINK_TAG_PREFIX = Glib::ustring{CtConst::TAG_LINK_PREFIX} + CtConst::LINK_TYPE_NODE + CtConst::CHAR_SPACE;

bool buffer_links_to(const Glib::RefPtr<Gtk::TextBuffer>& buffer, const std::set<gint64>& target_ids)
{
    if (not buffer) return false;
    Gtk::TextIter iter = buffer->begin();
    do {
        for (const Glib::RefPtr<Gtk::TextTag>& tag : iter.get_toggled_tags(true/*toggled_on*/)) {
            const std::optional<gint64> node_id = CtBacklinks::node_id_from_link_tag(tag->property_name().get_value());
            if (node_id and target_ids.count(*node_id)) return true;
        }
    } while (iter.forward_to_tag_toggle(Glib::RefPtr<Gtk::TextTag>{}));
    return false;
}

} // namespace

namespace CtBacklinks {

std::optional<gint64> node_id_from_link_tag(const Glib::ustring& tag_name)
{
    if (not str::startswith(tag_name, NODE_LINK_TAG_PREFIX)) return std::nullopt;
    const std::string rest = tag_name.substr(NODE_LINK_TAG_PREFIX.size()).raw();
    size_t digits = 0;
    while (digits < rest.size() and g_ascii_isdigit(rest[digits])) ++digits;
    if (digits == 0 or (digits < rest.size() and rest[digits] != ' ')) return std::nullopt;
    return g_ascii_strtoll(rest.substr(0, digits).c_str(), nullptr, 10);
}

std::vector<gint64> linking_node_ids(CtTreeStore& tree_store, const gint64 target_node_id)
{
    CtTreeIter target = tree_store.get_node_from_node_id(target_node_id);
    if (not target) return {};
    const gint64 target_holder = target.get_node_id_data_holder();

    // a link may point at the content holder or at any clone of it
    std::set<gint64> target_ids{target_node_id, target_holder};
    tree_store.get_store()->foreach_iter([&](const Gtk::TreeModel::iterator& iter) {
        CtTreeIter ct_iter = tree_store.to_ct_tree_iter(iter);
        if (ct_iter.get_node_id_data_holder() == target_holder) target_ids.insert(ct_iter.get_node_id());
        return false; /* continue */
    });

    std::vector<gint64> linking;
    std::set<gint64> visited_holders{target_holder};
    tree_store.get_store()->foreach_iter([&](const Gtk::TreeModel::iterator& iter) {
        CtTreeIter ct_iter = tree_store.to_ct_tree_iter(iter);
        const gint64 holder = ct_iter.get_node_id_data_holder();
        if (visited_holders.insert(holder).second and
            ct_iter.get_node_is_rich_text() and
            buffer_links_to(ct_iter.get_node_text_buffer(), target_ids))
        {
            linking.push_back(holder);
        }
        return false; /* continue */
    });
    return linking;
}

} // namespace CtBacklinks

// CtActions member kept here so the upstream file only gains the declaration
void CtActions::node_backlinks()
{
    if (not _is_there_selected_node_or_error()) return;
    CtTreeStore& tree_store = _pCtMainWin->get_tree_store();
    CtTreeIter curr_iter = _pCtMainWin->curr_tree_iter();
    const std::vector<gint64> linking = CtBacklinks::linking_node_ids(tree_store, curr_iter.get_node_id());
    if (linking.empty()) {
        CtDialogs::info_dialog(str::format(_("No Other Node Links to \"%s\"."), str::xml_escape(curr_iter.get_node_name())), *_pCtMainWin);
        return;
    }

    auto rItemStore = CtChooseDialogListStore::create();
    for (const gint64 node_id : linking) {
        CtTreeIter linking_iter = tree_store.get_node_from_node_id(node_id);
        rItemStore->add_row("ct_node_link",
                            linking_iter.get_node_name(),
                            CtMiscUtil::get_node_hierarchical_name(linking_iter, " / ", false/*for_filename*/),
                            node_id);
    }
    const Gtk::TreeModel::iterator chosen = CtDialogs::choose_item_dialog(*_pCtMainWin,
                                                                          str::format(_("Backlinks to \"%s\""), curr_iter.get_node_name().raw()),
                                                                          rItemStore);
    if (not chosen) return;
    CtTreeIter chosen_iter = tree_store.get_node_from_node_id(chosen->get_value(rItemStore->columns.node_id));
    if (chosen_iter) {
        _pCtMainWin->get_tree_view().set_cursor_safe(chosen_iter);
    }
}
