/*
 * ct_templates.cc
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

#include "ct_templates.h"
#include "ct_actions.h"
#include "ct_dialogs.h"
#include "ct_main_win.h"
#include <ctime>

namespace {

const Glib::ustring TEMPLATES_ROOT_NAME{"Templates"};

Glib::ustring placeholder(const std::string& key)
{
    return "{{" + key + "}}";
}

Glib::ustring replace_all(Glib::ustring text, const Glib::ustring& from, const Glib::ustring& to)
{
    for (size_t pos = text.find(from); pos != Glib::ustring::npos; pos = text.find(from, pos + to.size())) {
        text.replace(pos, from.size(), to);
    }
    return text;
}

Glib::ustring now_formatted(const char* format)
{
    const std::time_t now = std::time(nullptr);
    char formatted[32]{};
    std::strftime(formatted, sizeof(formatted), format, std::localtime(&now));
    return formatted;
}

void fill_node_and_children(CtTreeStore& tree_store,
                            const Gtk::TreeModel::iterator& iter,
                            const CtTemplates::Values& values,
                            const bool is_top)
{
    CtTreeIter ct_iter = tree_store.to_ct_tree_iter(iter);
    const auto title = values.find("title");
    ct_iter.set_node_name(is_top and title != values.end() ? title->second : CtTemplates::fill(ct_iter.get_node_name(), values));
    CtTemplates::fill_buffer(ct_iter.get_node_text_buffer(), values);
    for (const Gtk::TreeModel::iterator& child : iter->children()) {
        fill_node_and_children(tree_store, child, values, false/*is_top*/);
    }
}

} // namespace

namespace CtTemplates {

Values default_values(const Glib::ustring& title)
{
    return Values{{"title", title}, {"date", now_formatted("%Y-%m-%d")}, {"time", now_formatted("%H:%M")}};
}

Glib::ustring fill(const Glib::ustring& text, const Values& values)
{
    Glib::ustring filled = text;
    for (const auto& [key, value] : values) {
        filled = replace_all(filled, placeholder(key), value);
    }
    return filled;
}

void fill_buffer(const Glib::RefPtr<Gtk::TextBuffer>& buffer, const Values& values)
{
    if (not buffer) return;
    for (const auto& [key, value] : values) {
        const Glib::ustring needle = placeholder(key);
        int search_from = 0;
        Gtk::TextIter match_start, match_end;
        while (buffer->get_iter_at_offset(search_from).forward_search(needle, static_cast<Gtk::TextSearchFlags>(0), match_start, match_end)) {
            const int start_offset = match_start.get_offset();
            const std::vector<Glib::RefPtr<Gtk::TextTag>> tags = match_start.get_tags();
            buffer->insert_with_tags(buffer->erase(match_start, match_end), value, tags);
            search_from = start_offset + static_cast<int>(value.size());
        }
    }
}

CtTreeIter templates_root(CtTreeStore& tree_store)
{
    for (const Gtk::TreeModel::iterator& iter : tree_store.get_store()->children()) {
        CtTreeIter ct_iter = tree_store.to_ct_tree_iter(iter);
        if (ct_iter.get_node_name().casefold() == TEMPLATES_ROOT_NAME.casefold()) return ct_iter;
    }
    return tree_store.to_ct_tree_iter(Gtk::TreeModel::iterator{});
}

std::vector<CtTreeIter> templates(CtTreeStore& tree_store)
{
    std::vector<CtTreeIter> found;
    CtTreeIter root = templates_root(tree_store);
    if (not root) return found;
    for (const Gtk::TreeModel::iterator& iter : root->children()) {
        found.push_back(tree_store.to_ct_tree_iter(iter));
    }
    return found;
}

bool is_within_templates(CtTreeStore& tree_store, const CtTreeIter& iter)
{
    CtTreeIter root = templates_root(tree_store);
    return root and iter and (iter == root or tree_store.get_store()->is_ancestor(root, iter));
}

Gtk::TreeModel::iterator instantiate(CtMainWin* pCtMainWin, CtTreeIter template_iter, const Values& values)
{
    CtTreeStore& tree_store = pCtMainWin->get_tree_store();
    if (is_within_templates(tree_store, pCtMainWin->curr_tree_iter())) {
        // the copy would land among the templates: put it after the Templates node instead
        pCtMainWin->get_tree_view().set_cursor_safe(templates_root(tree_store));
    }
    pCtMainWin->get_ct_actions()->node_subnodes_paste2(template_iter, pCtMainWin);
    Gtk::TreeModel::iterator new_top = pCtMainWin->curr_tree_iter();
    fill_node_and_children(tree_store, new_top, values, true/*is_top*/);
    return new_top;
}

} // namespace CtTemplates

// CtActions member kept here so the upstream file only gains the declaration
void CtActions::node_from_template()
{
    CtTreeStore& tree_store = _pCtMainWin->get_tree_store();
    const std::vector<CtTreeIter> template_iters = CtTemplates::templates(tree_store);
    if (template_iters.empty()) {
        CtDialogs::info_dialog(_("To use templates, create a top-level node named \"Templates\" and put template nodes under it.\n\n"
                                 "In node names and text, {{title}}, {{date}} and {{time}} are filled in when a node is created from a template."),
                               *_pCtMainWin);
        return;
    }

    auto rItemStore = CtChooseDialogListStore::create();
    for (const CtTreeIter& template_iter : template_iters) {
        rItemStore->add_row("ct_tree-node-dupl", template_iter.get_node_name(), "", template_iter.get_node_id());
    }
    const Gtk::TreeModel::iterator chosen = CtDialogs::choose_item_dialog(*_pCtMainWin, _("New Node from Template"), rItemStore, _("Template"));
    if (not chosen) return;
    CtTreeIter template_iter = tree_store.get_node_from_node_id(chosen->get_value(rItemStore->columns.node_id));
    if (not template_iter) return;

    // suggest the template's own name with everything but the title filled in, e.g. "Meeting 2026-10-05"
    const Glib::ustring suggested = CtTemplates::fill(template_iter.get_node_name(), CtTemplates::default_values(""));
    const Glib::ustring title = CtDialogs::img_n_entry_dialog(*_pCtMainWin, _("New Node Name"), suggested, "ct_tree-node-add");
    if (title.empty()) return;
    (void)CtTemplates::instantiate(_pCtMainWin, template_iter, CtTemplates::default_values(title));
}
