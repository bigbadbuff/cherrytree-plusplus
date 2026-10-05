/*
 * tests_backlinks.cpp
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
#include "ct_const.h"
#include "ct_main_win.h"
#include "tests_common.h"
#include "tests_plusplus_app.h"

TEST(BacklinksGroup, ParsesNodeIdsFromLinkTagNames)
{
    ASSERT_EQ(std::optional<gint64>{4}, CtBacklinks::node_id_from_link_tag("link_node 4"));
    ASSERT_EQ(std::optional<gint64>{5}, CtBacklinks::node_id_from_link_tag("link_node 5 йцукенгшщз"));
    ASSERT_FALSE(CtBacklinks::node_id_from_link_tag("link_webs http://www.ansa.it").has_value());
    ASSERT_FALSE(CtBacklinks::node_id_from_link_tag("weight_heavy").has_value());
    ASSERT_FALSE(CtBacklinks::node_id_from_link_tag("link_node x").has_value());
    ASSERT_FALSE(CtBacklinks::node_id_from_link_tag("link_node 4x").has_value());
    ASSERT_FALSE(CtBacklinks::node_id_from_link_tag("link_node ").has_value());
}

TEST(BacklinksGroup, FindsNodesLinkingToTarget)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_TRUE(pWin->file_open(UT::testCtbDocPath, ""/*node_to_focus*/, ""/*anchor_to_focus*/));
        CtTreeStore& store = pWin->get_tree_store();

        // node 'e' (5) links to node 'd' (4) and to itself; node 10 is a clone of 'e'
        ASSERT_EQ(std::vector<gint64>{5}, CtBacklinks::linking_node_ids(store, 4));
        ASSERT_TRUE(CtBacklinks::linking_node_ids(store, 5).empty());  // self-links don't count
        ASSERT_TRUE(CtBacklinks::linking_node_ids(store, 10).empty()); // nor do they for its clone
        ASSERT_TRUE(CtBacklinks::linking_node_ids(store, 1).empty());
        ASSERT_TRUE(CtBacklinks::linking_node_ids(store, 999).empty()); // unknown node

        // a new link from node 'b' (2) to 'd' (4) is found, in tree order
        CtTreeIter node_b = store.get_node_from_node_id(2);
        auto buffer = node_b.get_node_text_buffer();
        const std::string tag_name = pWin->get_text_tag_name_exist_or_create(CtConst::TAG_LINK, "node 4");
        buffer->insert_with_tag(buffer->end(), "see d", tag_name);
        ASSERT_EQ((std::vector<gint64>{2, 5}), CtBacklinks::linking_node_ids(store, 4));
    });
}

TEST(BacklinksGroup, ActionIsRegistered)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_NE(nullptr, pWin->get_ct_menu().find_action("node_backlinks"));
    });
}

TEST(BacklinksGroup, LinksToAClonePointAtTheSameContent)
{
    run_with_hidden_window([](CtMainWin* pWin) {
        ASSERT_TRUE(pWin->file_open(UT::testCtbDocPath, ""/*node_to_focus*/, ""/*anchor_to_focus*/));
        CtTreeStore& store = pWin->get_tree_store();

        // node 'b' (2) links to node 10, a clone of 'e' (5): that is a backlink of 'e' too
        auto buffer = store.get_node_from_node_id(2).get_node_text_buffer();
        buffer->insert_with_tag(buffer->end(), "see clone", pWin->get_text_tag_name_exist_or_create(CtConst::TAG_LINK, "node 10"));

        ASSERT_EQ(std::vector<gint64>{2}, CtBacklinks::linking_node_ids(store, 5));
        ASSERT_EQ(std::vector<gint64>{2}, CtBacklinks::linking_node_ids(store, 10));
    });
}
