/*
 * tests_templates.cpp
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
#include "ct_slash_menu.h"
#include <algorithm>
#include "ct_main_win.h"
#include "tests_common.h"
#include "tests_plusplus_app.h"
#include <gtkmm/main.h>

namespace {

// Projects(1), Templates(2) > [ "Meeting {{date}}"(3) > Notes(4), Daily(5) ]
const std::string fixturePath{Glib::build_filename(UT::unitTestsDataDir, "templates_fixture.ctb")};
const CtTemplates::Values testValues{{"title", "Kickoff"}, {"date", "2026-10-05"}, {"time", "09:30"}};

void open_fixture_copy(CtMainWin* pWin)
{
    const fs::path doc_path = pWin->get_ct_tmp()->getHiddenDirPath("UT") / "templates.ctb";
    ASSERT_TRUE(fs::copy_file(fixturePath, doc_path));
    ASSERT_TRUE(pWin->file_open(doc_path, ""/*node_to_focus*/, ""/*anchor_to_focus*/));
}

Glib::ustring text_of(CtTreeIter iter)
{
    return iter.get_node_text_buffer()->get_text();
}

std::vector<Glib::ustring> top_level_names(CtTreeStore& store)
{
    std::vector<Glib::ustring> names;
    for (const auto& row : store.get_store()->children()) {
        names.push_back(store.to_ct_tree_iter(row).get_node_name());
    }
    return names;
}

} // namespace

TEST(TemplatesGroup, FillsKnownPlaceholdersOnly)
{
    ASSERT_STREQ("Meeting 2026-10-05", CtTemplates::fill("Meeting {{date}}", testValues).c_str());
    ASSERT_STREQ("Kickoff at 09:30, Kickoff", CtTemplates::fill("{{title}} at {{time}}, {{title}}", testValues).c_str());
    ASSERT_STREQ("{{unknown}} and {title}", CtTemplates::fill("{{unknown}} and {title}", testValues).c_str());
}

TEST(TemplatesGroup, DefaultValuesHaveTitleDateAndTime)
{
    const CtTemplates::Values values = CtTemplates::default_values("Plan");
    ASSERT_STREQ("Plan", values.at("title").c_str());
    ASSERT_EQ(10u, values.at("date").size()); // YYYY-MM-DD
    ASSERT_EQ(5u, values.at("time").size());  // HH:MM
}

TEST(TemplatesGroup, FillsBufferKeepingFormatting)
{
    (void)gtk_init_check(nullptr, nullptr);
    Glib::init();
    Gtk::Main::init_gtkmm_internals();
    auto buffer = Gtk::TextBuffer::create();
    auto bold = buffer->create_tag("bold");
    buffer->insert(buffer->end(), "Notes for ");
    buffer->insert_with_tag(buffer->end(), "{{title}}", bold);
    buffer->insert(buffer->end(), " on {{date}}");

    CtTemplates::fill_buffer(buffer, testValues);

    ASSERT_STREQ("Notes for Kickoff on 2026-10-05", buffer->get_text().c_str());
    Gtk::TextIter kickoff = buffer->get_iter_at_offset(10);
    ASSERT_TRUE(kickoff.has_tag(bold));
    ASSERT_FALSE(buffer->get_iter_at_offset(20).has_tag(bold));
}

TEST(TemplatesGroup, ListsTheTemplatesNodeChildren)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        open_fixture_copy(pWin);
        CtTreeStore& store = pWin->get_tree_store();

        ASSERT_STREQ("Templates", CtTemplates::templates_root(store).get_node_name().c_str());
        std::vector<Glib::ustring> names;
        for (CtTreeIter iter : CtTemplates::templates(store)) names.push_back(iter.get_node_name());
        ASSERT_EQ((std::vector<Glib::ustring>{"Meeting {{date}}", "Daily"}), names);
    });
}

TEST(TemplatesGroup, NoTemplatesNodeMeansNoTemplates)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_TRUE(pWin->file_open(UT::testCtbDocPath, ""/*node_to_focus*/, ""/*anchor_to_focus*/));
        ASSERT_FALSE(CtTemplates::templates_root(pWin->get_tree_store()));
        ASSERT_TRUE(CtTemplates::templates(pWin->get_tree_store()).empty());
    });
}

TEST(TemplatesGroup, InstantiatesTheSubtreeAfterTheCurrentNode)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        open_fixture_copy(pWin);
        CtTreeStore& store = pWin->get_tree_store();
        pWin->get_tree_view().set_cursor_safe(store.get_node_from_node_id(1)); // Projects

        CtTreeIter created = store.to_ct_tree_iter(CtTemplates::instantiate(pWin, store.get_node_from_node_id(3), testValues));

        ASSERT_EQ((std::vector<Glib::ustring>{"Projects", "Kickoff", "Templates"}), top_level_names(store));
        ASSERT_STREQ("Kickoff\nDate: 2026-10-05 at 09:30\n☐ agenda\n", text_of(created).c_str());
        CtTreeIter child = store.to_ct_tree_iter(created->children().begin());
        ASSERT_STREQ("Notes", child.get_node_name().c_str());
        ASSERT_STREQ("Notes for Kickoff\n", text_of(child).c_str());
        // the template itself is untouched
        ASSERT_STREQ("Meeting {{date}}", store.get_node_from_node_id(3).get_node_name().c_str());
        ASSERT_TRUE(text_of(store.get_node_from_node_id(3)).raw().find("{{title}}") != std::string::npos);
    });
}

// Decides whether instantiate() moves the selection to the Templates node first, so the copy lands
// after it rather than among the templates. (Changing the selection inside the Templates subtree is
// not driven here: GTK's text layout misbehaves in a never-shown window.)
TEST(TemplatesGroup, KnowsWhichNodesAreWithinTemplates)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        open_fixture_copy(pWin);
        CtTreeStore& store = pWin->get_tree_store();

        ASSERT_TRUE(CtTemplates::is_within_templates(store, store.get_node_from_node_id(2)));  // Templates
        ASSERT_TRUE(CtTemplates::is_within_templates(store, store.get_node_from_node_id(4)));  // ... > Notes
        ASSERT_FALSE(CtTemplates::is_within_templates(store, store.get_node_from_node_id(1))); // Projects
        ASSERT_FALSE(CtTemplates::is_within_templates(store, store.to_ct_tree_iter(Gtk::TreeModel::iterator{})));
    });
}

TEST(TemplatesGroup, ActionIsRegisteredAndOfferedInTheSlashMenu)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_NE(nullptr, pWin->get_ct_menu().find_action("node_from_template"));
    });
    const auto& slash_ids = CtSlashMenu::action_ids();
    ASSERT_NE(slash_ids.end(), std::find(slash_ids.begin(), slash_ids.end(), "node_from_template"));
}
