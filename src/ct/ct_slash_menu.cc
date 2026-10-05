/*
 * ct_slash_menu.cc
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

#include "ct_slash_menu.h"
#include "ct_const.h"
#include "ct_dialogs.h"
#include "ct_main_win.h"
#include "ct_text_view.h"

namespace CtSlashMenu {

const std::vector<std::string>& action_ids()
{
    static const std::vector<std::string> ids{
        "fmt_h1", "fmt_h2", "fmt_h3",
        "handle_bull_list", "handle_num_list", "handle_todo_list",
        "handle_table", "handle_codebox", "insert_horiz_rule",
        "handle_link", "handle_image", "handle_embfile", "handle_anchor",
        "insert_toc", "insert_timestamp", "handle_latex", "insert_special_char",
        "tree_add_subnode", "node_from_template",
    };
    return ids;
}

bool is_trigger(const Gtk::TextIter& iter_after_slash)
{
    Gtk::TextIter iter = iter_after_slash;
    if (not iter.backward_char() or iter.get_char() != '/') return false;
    while (iter.backward_char()) {
        const gunichar ch = iter.get_char();
        if (ch == '\n') return true;
        if (ch != ' ' and ch != '\t') return false;
    }
    return true; // reached the start of the buffer
}

std::string heading_scale_for_action(const std::string& action_id)
{
    if (action_id == "fmt_h1") return CtConst::TAG_PROP_VAL_H1;
    if (action_id == "fmt_h2") return CtConst::TAG_PROP_VAL_H2;
    if (action_id == "fmt_h3") return CtConst::TAG_PROP_VAL_H3;
    return "";
}

} // namespace CtSlashMenu

CtStickyLineTag::~CtStickyLineTag()
{
    detach();
}

void CtStickyLineTag::attach(Glib::RefPtr<Gtk::TextBuffer> buffer, const Gtk::TextIter& iter_on_line, const Glib::ustring& tag_name)
{
    detach();
    Gtk::TextIter line_start = iter_on_line;
    line_start.set_line_offset(0);
    _buffer = buffer;
    _tagName = tag_name;
    _lineMark = _buffer->create_mark(line_start, true/*left_gravity*/);
    _connection = _buffer->signal_insert().connect(sigc::mem_fun(*this, &CtStickyLineTag::_on_insert), true/*after*/);
}

void CtStickyLineTag::detach()
{
    _connection.disconnect();
    if (_buffer and _lineMark and not _lineMark->get_deleted()) {
        _buffer->delete_mark(_lineMark);
    }
    _lineMark.reset();
    _buffer.reset();
}

void CtStickyLineTag::_on_insert(const Gtk::TextIter& iter_after_insert, const Glib::ustring& text, int /*bytes*/)
{
    Gtk::TextIter iter_start = iter_after_insert;
    iter_start.backward_chars(static_cast<int>(text.size()));
    if (text.find('\n') != Glib::ustring::npos or iter_start.get_line() != _lineMark->get_iter().get_line()) {
        detach();
        return;
    }
    _buffer->apply_tag_by_name(_tagName, iter_start, iter_after_insert);
}

// CtTextView member kept here so the upstream file only gains the hook
void CtTextView::_open_slash_menu(const int slash_offset)
{
    const std::string action_id = CtDialogs::dialog_palette(_pCtMainWin, CtSlashMenu::action_ids());
    if (action_id.empty()) return; // Esc: the '/' stays as typed
    CtMenuAction* pAction = _pCtMainWin->get_ct_menu().find_action(action_id);
    auto text_buffer = get_buffer();
    Gtk::TextIter iter_slash = text_buffer->get_iter_at_offset(slash_offset);
    if (not pAction or iter_slash.get_char() != '/') return; // the text changed meanwhile

    Gtk::TextIter iter_after_slash = iter_slash;
    iter_after_slash.forward_char();
    text_buffer->erase(iter_slash, iter_after_slash);
    text_buffer->place_cursor(text_buffer->get_iter_at_offset(slash_offset));
    mm().grab_focus();

    pAction->run_action();

    const std::string scale = CtSlashMenu::heading_scale_for_action(action_id);
    Gtk::TextIter iter_insert = text_buffer->get_insert()->get_iter();
    if (not scale.empty() and iter_insert.starts_line() and iter_insert.ends_line()) {
        // empty line: there is nothing to format yet, so format what gets typed next
        _stickyLineTag.attach(text_buffer, iter_insert, _pCtMainWin->get_text_tag_name_exist_or_create(CtConst::TAG_SCALE, scale));
    }
}
