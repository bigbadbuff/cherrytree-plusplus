/*
 * tests_slash_menu.cpp
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
#include "ct_main_win.h"
#include "tests_common.h"
#include "tests_plusplus_app.h"
#include <gtkmm/main.h>

namespace {

// gtkmm wrappers (e.g. Gtk::TextTag) need GTK's types registered, not just Glib::init();
// gtk_init_check() does that and simply returns false when there is no display
void init_gtkmm()
{
    (void)gtk_init_check(nullptr, nullptr);
    Glib::init();
    Gtk::Main::init_gtkmm_internals();
}

bool has_tag_everywhere(const Gtk::TextIter& from, const Gtk::TextIter& to, const Glib::RefPtr<Gtk::TextTag>& tag)
{
    for (Gtk::TextIter it = from; it < to; it.forward_char()) {
        if (not it.has_tag(tag)) return false;
    }
    return true;
}

Glib::ustring line_text(const Glib::RefPtr<Gtk::TextBuffer>& buffer, const int line)
{
    Gtk::TextIter start = buffer->get_iter_at_line(line);
    Gtk::TextIter end = start;
    if (not end.ends_line()) end.forward_to_line_end();
    return buffer->get_text(start, end);
}

} // namespace

TEST(SlashMenuGroup, TriggersOnlyWhenSlashStartsTheLine)
{
    init_gtkmm();
    auto buffer = Gtk::TextBuffer::create();
    const std::vector<std::pair<Glib::ustring, bool>> cases{
        {"/", true}, {"   /", true}, {"\t/", true}, {"intro\n/", true}, {"intro\n  /", true},
        {"a/", false}, {"http:/", false}, {"a /", false}, {"//", false}, {"intro\nx/", false}, {"", false},
    };
    for (const auto& [text, expected] : cases) {
        buffer->set_text(text);
        ASSERT_EQ(expected, CtSlashMenu::is_trigger(buffer->end())) << "text: '" << text << "'";
    }
}

TEST(SlashMenuGroup, HeadingActionsMapToScaleValues)
{
    ASSERT_STREQ("h1", CtSlashMenu::heading_scale_for_action("fmt_h1").c_str());
    ASSERT_STREQ("h3", CtSlashMenu::heading_scale_for_action("fmt_h3").c_str());
    ASSERT_TRUE(CtSlashMenu::heading_scale_for_action("handle_table").empty());
}

TEST(SlashMenuGroup, StickyTagFormatsWhatIsTypedOnItsLine)
{
    init_gtkmm();
    auto buffer = Gtk::TextBuffer::create();
    auto tag = buffer->create_tag("scale_h1");
    buffer->set_text("intro\n\nafter");
    CtStickyLineTag sticky;

    sticky.attach(buffer, buffer->get_iter_at_line(1), "scale_h1");
    buffer->insert(buffer->get_iter_at_line(1), "Tit");
    Gtk::TextIter line_end = buffer->get_iter_at_line(1);
    line_end.forward_to_line_end();
    buffer->insert(line_end, "le");

    ASSERT_STREQ("Title", line_text(buffer, 1).c_str());
    Gtk::TextIter title_end = buffer->get_iter_at_line(1);
    title_end.forward_to_line_end();
    ASSERT_TRUE(has_tag_everywhere(buffer->get_iter_at_line(1), title_end, tag));
    ASSERT_TRUE(sticky.is_attached());
}

TEST(SlashMenuGroup, StickyTagEndsAtNewlineAndDoesNotLeak)
{
    init_gtkmm();
    auto buffer = Gtk::TextBuffer::create();
    auto tag = buffer->create_tag("scale_h1");
    buffer->set_text("intro\n");
    CtStickyLineTag sticky;

    sticky.attach(buffer, buffer->get_iter_at_line(1), "scale_h1");
    buffer->insert(buffer->end(), "Title");
    buffer->insert(buffer->end(), "\n");
    ASSERT_FALSE(sticky.is_attached());
    buffer->insert(buffer->end(), "body");

    ASSERT_STREQ("body", line_text(buffer, 2).c_str());
    ASSERT_FALSE(buffer->get_iter_at_line(2).has_tag(tag));
}

TEST(SlashMenuGroup, StickyTagEndsWhenTypingOnAnotherLine)
{
    init_gtkmm();
    auto buffer = Gtk::TextBuffer::create();
    auto tag = buffer->create_tag("scale_h1");
    buffer->set_text("intro\n");
    CtStickyLineTag sticky;

    sticky.attach(buffer, buffer->get_iter_at_line(1), "scale_h1");
    buffer->insert(buffer->begin(), "x");

    ASSERT_FALSE(sticky.is_attached());
    ASSERT_FALSE(buffer->begin().has_tag(tag));
}

TEST(SlashMenuGroup, EveryOfferedActionExists)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_FALSE(CtSlashMenu::action_ids().empty());
        for (const std::string& id : CtSlashMenu::action_ids()) {
            ASSERT_NE(nullptr, pWin->get_ct_menu().find_action(id)) << id;
        }
    });
}
