/*
 * tests_external_update.cpp
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

// When another program (e.g. the Claude MCP server) writes to the open document and CherryTree
// then saves before its "Reload After External Update" sentinel polled, the save must not record
// the post-save mod time: otherwise the sentinel never sees the outside change and the app keeps
// (and may later write back) a stale copy of the nodes the other program changed.

#include "ct_app.h"
#include "ct_filesystem.h"
#include "ct_storage_control.h"
#include "tests_common.h"
#include <glib/gstdio.h>
#ifdef _WIN32
#include <sys/utime.h>
#else
#include <utime.h>
#endif

namespace {

constexpr time_t OUTSIDE_WRITE_DELAY_SECONDS = 10;

class ExternalUpdateTestApp : public CtApp
{
public:
    explicit ExternalUpdateTestApp(const bool simulate_outside_write)
     : CtApp{"_test_external_update"}
     , _simulateOutsideWrite{simulate_outside_write}
    {
        _no_gui = true;
    }

private:
    void on_activate() final
    {
        _on_startup();
        _run_test();
    }

    void _run_test()
    {
        CtMainWin* pWin = _create_window(true/*start_hidden*/);
        const fs::path doc_path = pWin->get_ct_tmp()->getHiddenDirPath("UT") / "external_update.ctb";
        ASSERT_TRUE(fs::copy_file(UT::testCtbDocPath, doc_path));
        ASSERT_TRUE(pWin->file_open(doc_path, ""/*node_to_focus*/, ""/*anchor_to_focus*/));
        const time_t mod_time_at_load = pWin->get_ct_storage()->get_mod_time();
        ASSERT_GT(mod_time_at_load, 0);

        // a local, unsaved edit
        CtTreeIter ctTreeIter = pWin->get_tree_store().get_node_from_node_name("e");
        auto pTextBuffer = ctTreeIter.get_node_text_buffer();
        pTextBuffer->insert(pTextBuffer->end(), "local edit");
        pWin->update_window_save_needed(CtSaveNeededUpdType::nbuf, false/*new_machine_state*/, &ctTreeIter);

        if (_simulateOutsideWrite) {
            struct utimbuf outside_write_time{};
            outside_write_time.actime = mod_time_at_load + OUTSIDE_WRITE_DELAY_SECONDS;
            outside_write_time.modtime = mod_time_at_load + OUTSIDE_WRITE_DELAY_SECONDS;
            ASSERT_EQ(0, g_utime(doc_path.c_str(), &outside_write_time));
        }

        ASSERT_TRUE(pWin->file_save(false/*need_vacuum*/));

        const time_t recorded = pWin->get_ct_storage()->get_mod_time();
        const time_t on_disk = fs::getmtime(doc_path);
        ASSERT_GT(recorded, 0); // the sentinel only polls with a positive recorded mod time
        if (_simulateOutsideWrite) {
            // still behind the file: the sentinel will reload and show the outside change
            ASSERT_LT(recorded, on_disk);
        }
        else {
            // unchanged behaviour: our own save is not mistaken for an outside change
            ASSERT_EQ(recorded, on_disk);
        }

        pWin->force_exit() = true;
        remove_window(*pWin);
    }

    const bool _simulateOutsideWrite;
};

void run_app(const bool simulate_outside_write)
{
    const std::vector<std::string> vec_args{"cherrytree"};
    gchar** pp_args = CtStrUtil::vector_to_array(vec_args);
    ExternalUpdateTestApp app{simulate_outside_write};
    app.run(static_cast<int>(vec_args.size()), pp_args);
    g_strfreev(pp_args);
}

} // namespace

TEST(ExternalUpdateTests, SaveAfterOutsideWriteKeepsReloadPending)
{
    run_app(true/*simulate_outside_write*/);
}

TEST(ExternalUpdateTests, PlainSaveRecordsNewModTime)
{
    run_app(false/*simulate_outside_write*/);
}
