/*
 * ct_slash_menu.h
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

#include <gtkmm/textbuffer.h>
#include <string>
#include <vector>

// CherryTree++: Notion-style "/" menu. Typing '/' at the start of a line (after optional
// indentation) in a rich text node opens the command palette restricted to insert/format actions.
namespace CtSlashMenu {

// Menu action ids offered by the "/" menu, in display order
const std::vector<std::string>& action_ids();

// Whether the character just before `iter_after_slash` is a '/' that starts its line
bool is_trigger(const Gtk::TextIter& iter_after_slash);

// "h1".."h3" for the heading actions, empty otherwise
std::string heading_scale_for_action(const std::string& action_id);

} // namespace CtSlashMenu

// Applies a tag to whatever is typed on one line, until a newline is typed or typing happens on
// another line. Lets "/" → Heading on an empty line format the text the user types next.
class CtStickyLineTag
{
public:
    CtStickyLineTag() = default;
    ~CtStickyLineTag();
    CtStickyLineTag(const CtStickyLineTag&) = delete;
    CtStickyLineTag& operator=(const CtStickyLineTag&) = delete;

    void attach(Glib::RefPtr<Gtk::TextBuffer> buffer, const Gtk::TextIter& iter_on_line, const Glib::ustring& tag_name);
    void detach();
    bool is_attached() const { return _connection.connected(); }

private:
    void _on_insert(const Gtk::TextIter& iter_after_insert, const Glib::ustring& text, int bytes);

    Glib::RefPtr<Gtk::TextBuffer> _buffer;
    Glib::RefPtr<Gtk::TextMark> _lineMark;
    Glib::ustring _tagName;
    sigc::connection _connection;
};
